"""Photo helpers used by photo_report.py to download listing photos per source.

realtor.com photo URLs come straight from HomeHarvest's own API response (see
normalize.py's `photo_urls` column) - no extra scraping needed, no blocking risk.

Redfin has no such field in its CSV export, so for redfin rows this falls back to
screen-scraping the listing page the same way the standalone redfin_photos.py does.
"""
from __future__ import annotations

import re
from pathlib import Path

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

REDFIN_PHOTO_URL_RE = re.compile(
    r"https?:\\?/\\?/[a-zA-Z0-9.\-]*cdn-redfin\.com\\?/photo\\?/[^\s\"'\\]+?\.(?:jpg|jpeg|png|webp)",
    re.IGNORECASE,
)


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text or "").strip()
    text = re.sub(r"\s+", "-", text)
    return text or "listing"


def realtor_photo_urls(photo_urls_field, max_photos: int) -> list[str]:
    if not photo_urls_field or not isinstance(photo_urls_field, str):
        return []
    urls = [u.strip() for u in photo_urls_field.split(",") if u.strip()]
    return urls[:max_photos]


def redfin_photo_urls(property_url: str, max_photos: int, proxy: str | None = None) -> list[str]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.redfin.com/",
        }
    )
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})

    session.get("https://www.redfin.com/", timeout=15)  # warm up cookies like a real browser visit
    resp = session.get(property_url, timeout=20)
    resp.raise_for_status()

    found = [u.replace("\\/", "/") for u in REDFIN_PHOTO_URL_RE.findall(resp.text)]
    seen: set[str] = set()
    unique = []
    for u in found:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique[:max_photos]


def download_photos(urls: list[str], out_dir: Path, proxy: str | None = None) -> int:
    if not urls:
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})

    saved = 0
    for i, url in enumerate(urls, start=1):
        ext = url.split("?")[0].rsplit(".", 1)[-1].lower()
        if ext not in ("jpg", "jpeg", "png", "webp"):
            ext = "jpg"
        dest = out_dir / f"{i:03d}.{ext}"
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            saved += 1
        except Exception as exc:  # noqa: BLE001 - keep going, report the failure, move to next photo
            print(f"    [{i:03d}] failed to download: {exc}")

    return saved

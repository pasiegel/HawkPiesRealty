"""Download all photos from a single Redfin listing page.

Standalone utility - only needs `requests` (already in requirements.txt), not the
rest of house_scout. Built the same way as house_scout/sources/redfin.py: Redfin
has no official API, so this fetches the public listing page HTML (server-rendered,
so the photo URLs are present without running JS) and extracts image URLs from
Redfin's photo CDN by pattern.

Because it's screen-scraping an undocumented page structure, it can break if Redfin
changes their markup - use --debug to save the fetched HTML for troubleshooting if
it finds 0 photos.

Usage:
    python redfin_photos.py https://www.redfin.com/TX/Abilene/117-Gulfstream-79602/home/179113145
    python redfin_photos.py <url> --out my_photos
    python redfin_photos.py <url> --proxy http://user:pass@host:port
    python redfin_photos.py <url> --debug
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

PHOTO_URL_RE = re.compile(
    r"https?:\\?/\\?/[a-zA-Z0-9.\-]*cdn-redfin\.com\\?/photo\\?/[^\s\"'\\]+?\.(?:jpg|jpeg|png|webp)",
    re.IGNORECASE,
)

# Earlier entries = larger/preferred resolution. Redfin's photo CDN paths encode size
# via folder/prefix keywords rather than explicit dimensions.
SIZE_PRIORITY = ["bigphoto", "genfull", "wide", "full", "genmid", "mid", "mbphoto", "thumb", "small"]


def fetch_html(url: str, proxy: str | None = None) -> str:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.redfin.com/",
        }
    )
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})

    session.get("https://www.redfin.com/", timeout=15)  # warm up cookies like a real browser visit
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    return resp.text


def _photo_group_key(url: str) -> str:
    """Collapse different size variants of the same photo down to one key."""
    tail = url.rsplit("/", 1)[-1]
    tail = re.sub(r"^(genmid|genfull|gensmall)\.", "", tail, flags=re.IGNORECASE)
    tail = re.sub(r"\.(jpg|jpeg|png|webp)$", "", tail, flags=re.IGNORECASE)
    tail = re.sub(r"^\d+_", "", tail)  # some variants prefix a shard/size number
    return tail


def _size_rank(url: str) -> int:
    lower = url.lower()
    for i, marker in enumerate(SIZE_PRIORITY):
        if marker in lower:
            return i
    return len(SIZE_PRIORITY)


def extract_photo_urls(html: str) -> list[str]:
    found = [u.replace("\\/", "/") for u in PHOTO_URL_RE.findall(html)]

    best_by_group: dict[str, str] = {}
    for url in found:
        key = _photo_group_key(url)
        if key not in best_by_group or _size_rank(url) < _size_rank(best_by_group[key]):
            best_by_group[key] = url
    return list(best_by_group.values())


def listing_folder_name(url: str) -> str:
    parts = [p for p in urlparse(url).path.split("/") if p]
    if "home" in parts:
        idx = parts.index("home")
        if idx > 0:
            return parts[idx - 1]
    return parts[-1] if parts else "redfin_listing"


def download_photos(urls: list[str], out_dir: Path, proxy: str | None = None) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Referer": "https://www.redfin.com/"})
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})

    saved = 0
    for i, url in enumerate(urls, start=1):
        ext = url.rsplit(".", 1)[-1].split("?")[0].lower()
        if ext not in ("jpg", "jpeg", "png", "webp"):
            ext = "jpg"
        dest = out_dir / f"{i:03d}.{ext}"
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            saved += 1
        except Exception as exc:  # noqa: BLE001 - keep going, report the failure, move to next photo
            print(f"  [{i:03d}] failed to download: {exc}")

    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description="Download all photos from a Redfin listing page.")
    parser.add_argument("url", help="Redfin listing URL")
    parser.add_argument("--out", default="redfin_photos", help="Base output folder (default: redfin_photos)")
    parser.add_argument("--proxy", default=None, help="Proxy URL, e.g. http://user:pass@host:port")
    parser.add_argument(
        "--debug", action="store_true", help="Save fetched HTML to debug.html if 0 photos are found"
    )
    args = parser.parse_args()

    print(f"Fetching {args.url} ...")
    try:
        html = fetch_html(args.url, proxy=args.proxy)
    except requests.exceptions.HTTPError as exc:
        print(f"Request failed: {exc}")
        if exc.response is not None and exc.response.status_code == 403:
            print(
                "Redfin's WAF often blocks cloud/datacenter IPs. Try running this from a home "
                "connection, or pass --proxy with a residential proxy."
            )
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001 - top-level CLI error handling
        print(f"Request failed: {exc}")
        sys.exit(1)

    urls = extract_photo_urls(html)
    print(f"Found {len(urls)} photo(s).")

    if not urls:
        if args.debug:
            Path("debug.html").write_text(html, encoding="utf-8")
            print(
                "No photos found - saved the fetched page to debug.html. Redfin may have changed "
                "its page structure; open debug.html and search for 'cdn-redfin' to see the "
                "current photo URL pattern, then update PHOTO_URL_RE in this script."
            )
        else:
            print("No photos found. Re-run with --debug to save the fetched HTML for troubleshooting.")
        sys.exit(1)

    out_dir = Path(args.out) / listing_folder_name(args.url)
    print(f"Downloading to {out_dir} ...")
    saved = download_photos(urls, out_dir, proxy=args.proxy)
    print(f"Saved {saved}/{len(urls)} photo(s) to {out_dir}")


if __name__ == "__main__":
    main()

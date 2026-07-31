"""Turn a house_scout report CSV into per-listing photo folders plus a ranked
Markdown writeup and a self-contained HTML slide deck.

Usage:
    python -m house_scout.photo_report --report reports/house_report_20260731_120000.csv
    python -m house_scout.photo_report --report <csv> --max-photos 15 --top 10
    python -m house_scout.photo_report --report <csv> --proxy http://user:pass@host:port
"""
from __future__ import annotations

import argparse
import base64
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd

from . import photos as photos_mod


def _num(value, fmt: str) -> str:
    try:
        if pd.isna(value):
            return "n/a"
        return format(value, fmt)
    except (TypeError, ValueError):
        return "n/a"


def _rationale(row: pd.Series) -> str:
    parts = []
    ppsf = row.get("score_price_per_sqft")
    dom = row.get("score_days_on_market")
    lot = row.get("score_lot_ratio")
    if pd.notna(ppsf):
        parts.append(f"cheaper per sqft than {ppsf:.0f}% of listings in this batch")
    if pd.notna(dom):
        parts.append(f"longer on market than {dom:.0f}% of them (more room to negotiate)")
    if pd.notna(lot):
        parts.append(f"more lot per sqft of house than {lot:.0f}% of them")
    if not parts:
        return "Not enough data to break down the score for this listing."
    return "Ranked here because it's " + "; ".join(parts) + "."


def _stretch_note(row: pd.Series) -> str | None:
    if not bool(row.get("stretch")):
        return None
    over = row.get("price_over_budget")
    dom = row.get("days_on_market")
    over_str = f"${over:,.0f}" if pd.notna(over) else "some amount"
    dom_str = f"{dom:.0f}" if pd.notna(dom) else "many"
    return (
        f"Over budget by {over_str}, but it's been on the market {dom_str} days - "
        f"a seller sitting that long may take an offer closer to your range."
    )


def _search_link(site: str, row: pd.Series) -> str:
    """Deep-link to a search engine result for this address on `site`, rather than
    the site itself - we never fetch Redfin/Zillow pages for listings we didn't
    already scrape, so we can't know their exact listing URL/ID. This still lands
    on the right listing almost every time without touching their servers at all.
    """
    parts = [str(row.get(f)) for f in ("address", "city", "state", "zip_code") if pd.notna(row.get(f))]
    query = " ".join(parts) + f" site:{site}"
    return f"https://www.google.com/search?q={quote_plus(query)}"


def _listing_links(row: pd.Series) -> list[tuple[str, str, bool]]:
    """Returns (label, url, is_direct) for each site - is_direct means it's the
    exact listing page (from a source we actually scraped); otherwise it's a
    best-effort search link.
    """
    source = str(row.get("source") or "")
    property_url = row.get("property_url")
    also_listed_at = row.get("also_listed_at")

    realtor_url = property_url if "realtor.com" in source and pd.notna(property_url) else None
    if source == "redfin" and pd.notna(property_url):
        redfin_url = property_url
    elif "realtor.com" in source and pd.notna(also_listed_at):
        redfin_url = also_listed_at
    else:
        redfin_url = None

    links = []
    links.append(("Realtor.com", realtor_url, True) if realtor_url else ("Search Realtor.com", _search_link("realtor.com", row), False))
    links.append(("Redfin", redfin_url, True) if redfin_url else ("Search Redfin", _search_link("redfin.com", row), False))
    links.append(("Search Zillow", _search_link("zillow.com", row), False))
    return links


def _folder_name(rank: int, address: str, city: str) -> str:
    return f"{rank:02d}_{photos_mod.slugify(f'{address} {city}')}"


def _cover_filename(listing_dir: Path) -> str | None:
    """First saved photo's actual filename - extension varies (webp/jpg/png) by source."""
    matches = sorted(listing_dir.glob("001.*")) if listing_dir.exists() else []
    return matches[0].name if matches else None


def _fetch_listing_photos(row: pd.Series, max_photos: int, proxy: str | None) -> list[str]:
    source = str(row.get("source") or "")
    if "redfin" in source and "realtor" not in source:
        try:
            return photos_mod.redfin_photo_urls(row.get("property_url"), max_photos, proxy=proxy)
        except Exception as exc:  # noqa: BLE001 - report and move on to the next listing
            print(f"    redfin photo fetch failed: {exc}")
            return []
    return photos_mod.realtor_photo_urls(row.get("photo_urls"), max_photos)


def _img_data_uri(path: Path) -> str | None:
    if not path.exists():
        return None
    ext = path.suffix.lstrip(".").lower()
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{data}"


def _write_markdown(out_path: Path, report_name: str, df: pd.DataFrame, folders: list[str]) -> None:
    lines = [
        "# House Ranking Report",
        "",
        f"Source: `{report_name}` — {len(df)} listings, ranked by `deal_score`",
        "(relative to the other listings in this batch only, not an absolute valuation).",
        "",
    ]
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        address = str(row.get("address") or "").strip()
        city = str(row.get("city") or "").strip()
        folder = folders[i - 1]
        cover_name = _cover_filename(out_path.parent / "photos" / folder)

        title = f"## {i}. {address}, {city} — deal score {_num(row.get('deal_score'), '.1f')}"
        if bool(row.get("stretch")):
            title += " `STRETCH`"
        lines.append(title)
        if cover_name:
            lines.append(f"![{address}](photos/{folder}/{cover_name})")
        lines.append("")
        lines.append(
            f"- **Price:** ${_num(row.get('list_price'), ',.0f')}"
            f"  **$/sqft:** ${_num(row.get('price_per_sqft'), ',.0f')}"
            f"  **Beds:** {_num(row.get('beds'), '.0f')}"
            f"  **Full baths:** {_num(row.get('full_baths'), '.0f')}"
            f"  **Sqft:** {_num(row.get('sqft'), ',.0f')}"
            f"  **Days on market:** {_num(row.get('days_on_market'), '.0f')}"
        )
        lines.append(f"- **Why ranked here:** {_rationale(row)}")
        stretch_note = _stretch_note(row)
        if stretch_note:
            lines.append(f"- **Stretch listing:** {stretch_note}")
        lines.append(f"- **Source:** {row.get('source')}")
        link_bits = [f"[{label}]({url})" + ("" if is_direct else " (search)") for label, url, is_direct in _listing_links(row)]
        lines.append(f"- **Listings:** {' | '.join(link_bits)}")
        lines.append(f"- **Photos:** `photos/{folder}/`")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


_SLIDE_CSS = """
:root { color-scheme: light dark; }
body { font-family: system-ui, sans-serif; margin: 0; padding: 2rem; max-width: 900px; margin-inline: auto; }
h1 { margin-bottom: 0.25rem; }
.subtitle { color: #888; margin-bottom: 2rem; }
.card {
  border: 1px solid rgba(128,128,128,0.35); border-radius: 12px; padding: 1.25rem;
  margin-bottom: 1.5rem; display: grid; grid-template-columns: 220px 1fr; gap: 1.25rem;
}
.card img { width: 220px; height: 165px; object-fit: cover; border-radius: 8px; }
.card .noimg {
  width: 220px; height: 165px; border-radius: 8px; background: rgba(128,128,128,0.15);
  display: flex; align-items: center; justify-content: center; color: #888; font-size: 0.85rem;
}
.rank { font-weight: 700; color: #888; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; }
.card h2 { margin: 0.15rem 0 0.5rem; font-size: 1.25rem; }
.price { font-weight: 600; margin-bottom: 0.4rem; }
.facts { color: #666; font-size: 0.9rem; margin-bottom: 0.5rem; }
.why { font-size: 0.9rem; margin-bottom: 0.5rem; }
.links { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; }
.links a {
  font-size: 0.85rem; padding: 0.3rem 0.7rem; border-radius: 999px; text-decoration: none;
  border: 1px solid rgba(37,99,235,0.4);
}
.links a.direct { background: rgba(37,99,235,0.12); }
.links a.search { border-style: dashed; opacity: 0.8; }
a { color: #2563eb; }
.card.stretch { border-color: rgba(217,119,6,0.5); }
.badge-stretch {
  display: inline-block; font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.05em; color: #b45309; background: rgba(217,119,6,0.15);
  border-radius: 999px; padding: 0.15rem 0.55rem; margin-left: 0.5rem; vertical-align: middle;
}
.stretch-note {
  font-size: 0.85rem; margin-bottom: 0.5rem; padding: 0.5rem 0.7rem; border-radius: 8px;
  background: rgba(217,119,6,0.1); border: 1px solid rgba(217,119,6,0.3);
}
@media (max-width: 600px) { .card { grid-template-columns: 1fr; } .card img, .card .noimg { width: 100%; } }
"""


def _write_slide_deck(out_path: Path, photos_root: Path, df: pd.DataFrame, folders: list[str]) -> None:
    cards = []
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        address = str(row.get("address") or "").strip()
        city = str(row.get("city") or "").strip()
        folder = folders[i - 1]
        cover_name = _cover_filename(photos_root / folder)
        img_uri = _img_data_uri(photos_root / folder / cover_name) if cover_name else None
        img_html = f'<img src="{img_uri}" alt="{address}">' if img_uri else '<div class="noimg">No photo</div>'

        link_html = "".join(
            f'<a class="{"direct" if is_direct else "search"}" href="{url}" target="_blank" rel="noopener">{label}</a>'
            for label, url, is_direct in _listing_links(row)
        )

        is_stretch = bool(row.get("stretch"))
        stretch_note = _stretch_note(row)
        badge_html = '<span class="badge-stretch">Stretch</span>' if is_stretch else ""
        stretch_html = f'<div class="stretch-note">{stretch_note}</div>' if stretch_note else ""

        cards.append(
            f"""<section class="card{' stretch' if is_stretch else ''}">
  {img_html}
  <div>
    <div class="rank">#{i} &middot; deal score {_num(row.get('deal_score'), '.1f')}{badge_html}</div>
    <h2>{address}, {city}</h2>
    <div class="price">${_num(row.get('list_price'), ',.0f')} &middot; ${_num(row.get('price_per_sqft'), ',.0f')}/sqft</div>
    <div class="facts">{_num(row.get('beds'), '.0f')} bd &middot; {_num(row.get('full_baths'), '.0f')} full ba &middot; {_num(row.get('sqft'), ',.0f')} sqft &middot; {_num(row.get('days_on_market'), '.0f')} days on market</div>
    {stretch_html}
    <div class="why">{_rationale(row)}</div>
    <div class="links">{link_html}</div>
  </div>
</section>"""
        )

    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>House Ranking Slide Deck</title>
<style>{_SLIDE_CSS}</style></head>
<body>
<h1>House Ranking</h1>
<div class="subtitle">{len(df)} listings, ranked by deal_score (relative within this batch only)</div>
{''.join(cards)}
</body></html>"""

    out_path.write_text(html, encoding="utf-8")


def run(report_csv: str, out_dir: str | None, max_photos: int, top: int | None, proxy: str | None) -> Path:
    report_path = Path(report_csv)
    df = pd.read_csv(report_path)
    if top:
        df = df.head(top).reset_index(drop=True)

    base_out = Path(out_dir) if out_dir else report_path.parent / f"{report_path.stem}_photos"
    photos_root = base_out / "photos"
    base_out.mkdir(parents=True, exist_ok=True)

    folders = []
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        address = str(row.get("address") or "").strip()
        city = str(row.get("city") or "").strip()
        folder = _folder_name(i, address, city)
        folders.append(folder)

        urls = _fetch_listing_photos(row, max_photos, proxy)
        saved = photos_mod.download_photos(urls, photos_root / folder, proxy=proxy)
        print(f"[{i:02d}] {address}, {city}: {saved}/{len(urls)} photo(s) -> {photos_root / folder}")

    md_path = base_out / "ranking_report.md"
    _write_markdown(md_path, report_path.name, df, folders)

    slide_path = base_out / "slide_deck.html"
    _write_slide_deck(slide_path, photos_root, df, folders)

    print(f"\nWrote {md_path}")
    print(f"Wrote {slide_path}")
    return base_out


def main() -> None:
    parser = argparse.ArgumentParser(description="Download photos + build a ranked report from a house_scout CSV.")
    parser.add_argument("--report", required=True, help="Path to a house_scout report CSV")
    parser.add_argument("--out", default=None, help="Output folder (default: <report>_photos next to the CSV)")
    parser.add_argument("--max-photos", type=int, default=12, help="Max photos per listing (default: 12)")
    parser.add_argument("--top", type=int, default=None, help="Only process the top N rows (default: all)")
    parser.add_argument("--proxy", default=None, help="Proxy URL, e.g. http://user:pass@host:port")
    args = parser.parse_args()

    run(args.report, args.out, args.max_photos, args.top, args.proxy)


if __name__ == "__main__":
    main()

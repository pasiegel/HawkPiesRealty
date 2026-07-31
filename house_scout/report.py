from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from .scoring import add_score

SOURCE_PRIORITY = {"realtor.com": 0, "redfin": 1}


def _clean(value) -> str:
    return "" if pd.isna(value) else str(value)


def _address_key(row: pd.Series) -> str:
    addr = _clean(row.get("address"))
    zip_code = _clean(row.get("zip_code"))
    key = re.sub(r"[^A-Z0-9]", "", addr.upper())
    return f"{key}|{zip_code}"


def dedupe_listings(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse the same house pulled from multiple sources into one row.

    Keeps the row from the higher-priority source (realtor.com, for its agent/broker
    contact info) and records any other source(s) the listing was also found on.
    """
    if df.empty:
        return df

    df = df.copy()
    df["_key"] = df.apply(_address_key, axis=1)
    df["_priority"] = df["source"].map(SOURCE_PRIORITY).fillna(99)

    rows = []
    for key, group in df.groupby("_key", sort=False):
        if not key or key.startswith("|"):
            # No usable address - keep every row as-is rather than merging blindly.
            rows.extend(group.to_dict("records"))
            continue

        group = group.sort_values("_priority")
        primary = group.iloc[0].to_dict()
        other_sources = sorted(set(group["source"]) - {primary["source"]})
        primary["source"] = "+".join([primary["source"]] + other_sources)

        other_urls = [
            u for u in group["property_url"].tolist() if pd.notna(u) and u != primary["property_url"]
        ]
        primary["also_listed_at"] = other_urls[0] if other_urls else None
        rows.append(primary)

    out = pd.DataFrame(rows).drop(columns=["_key", "_priority"], errors="ignore")
    return out.reset_index(drop=True)


def filter_full_baths(df: pd.DataFrame, full_baths_min: float | None) -> pd.DataFrame:
    """Stricter than the API's baths_min, which counts a half-bath as 0.5.

    Rows where full_baths is unknown (e.g. Redfin, which doesn't split full/half in
    its CSV export) are kept rather than dropped, since we can't evaluate them.
    """
    if full_baths_min is None or df.empty:
        return df

    mask = df["full_baths"].isna() | (df["full_baths"] >= full_baths_min)
    return df[mask].reset_index(drop=True)


PENDING_STATUS_MARKERS = ("pending", "contingent", "under_contract", "under contract", "sold", "off_market")


def filter_active_only(df: pd.DataFrame, active_only: bool) -> pd.DataFrame:
    """Belt-and-suspenders status filter, on top of exclude_pending/status=9 at the API level.

    Catches anything that slips through a source's own filtering (e.g. a stale/mislabeled
    status), rather than trusting each source's server-side filter completely.
    """
    if not active_only or df.empty:
        return df

    status = df["status"].apply(_clean).str.lower()
    mask = ~status.str.contains("|".join(PENDING_STATUS_MARKERS))
    return df[mask].reset_index(drop=True)


# Maps a requested exclusion to the label substrings that identify it across sources -
# realtor.com's `style` field uses PropertyType enum values (e.g. "MOBILE"), Redfin's
# "PROPERTY TYPE" column uses its own free-text labels (e.g. "Manufactured").
PROPERTY_TYPE_EXCLUSION_MARKERS = {
    "mobile": ("mobile", "manufactured"),
    "land": ("land", "lot"),
    "farm": ("farm",),
    "multi_family": ("multi_family", "multi-family"),
}


def filter_excluded_property_types(df: pd.DataFrame, excluded_types: list[str] | None) -> pd.DataFrame:
    if not excluded_types or df.empty:
        return df

    markers = []
    for excluded in excluded_types:
        markers.extend(PROPERTY_TYPE_EXCLUSION_MARKERS.get(excluded.lower(), (excluded.lower(),)))

    style = df["style"].apply(_clean).str.lower()
    mask = ~style.str.contains("|".join(markers))
    return df[mask].reset_index(drop=True)


def apply_price_stretch(
    df: pd.DataFrame,
    price_max: float | None,
    stretch_price_max: float | None,
    stretch_dom_min: int,
) -> pd.DataFrame:
    """Keep in-budget listings (list_price <= price_max) plus "stretch" listings priced up
    to stretch_price_max that have sat on the market at least stretch_dom_min days - long
    enough that a motivated seller might accept an offer down near price_max. Everything
    else above price_max is dropped. Flags survivors above price_max via the `stretch` /
    `price_over_budget` columns so the report can call them out rather than blend them in.
    """
    if df.empty or price_max is None:
        df = df.copy()
        df["stretch"] = False
        df["price_over_budget"] = pd.NA
        return df

    df = df.copy()
    within_budget = df["list_price"].isna() | (df["list_price"] <= price_max)

    if stretch_price_max is not None:
        dom = pd.to_numeric(df["days_on_market"], errors="coerce")
        is_stretch = (
            df["list_price"].notna()
            & (df["list_price"] > price_max)
            & (df["list_price"] <= stretch_price_max)
            & (dom >= stretch_dom_min)
        )
    else:
        is_stretch = pd.Series(False, index=df.index)

    df["stretch"] = is_stretch
    df["price_over_budget"] = (df["list_price"] - price_max).where(is_stretch)

    return df[within_budget | is_stretch].reset_index(drop=True)


def build_report(
    source_frames: list[pd.DataFrame],
    full_baths_min: float | None = None,
    active_only: bool = True,
    excluded_property_types: list[str] | None = None,
    price_max: float | None = None,
    stretch_price_max: float | None = None,
    stretch_dom_min: int = 45,
) -> pd.DataFrame:
    frames = [f for f in source_frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined = dedupe_listings(combined)
    combined = filter_full_baths(combined, full_baths_min)
    combined = filter_active_only(combined, active_only)
    combined = filter_excluded_property_types(combined, excluded_property_types)
    combined = apply_price_stretch(combined, price_max, stretch_price_max, stretch_dom_min)
    combined = add_score(combined)
    combined = combined.sort_values("deal_score", ascending=False, na_position="last")
    return combined.reset_index(drop=True)


def export_csv(df: pd.DataFrame, output_dir: str, basename: str) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"{basename}_{timestamp}.csv"
    df.to_csv(out_path, index=False)
    return out_path

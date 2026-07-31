from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class SearchCriteria:
    location: str
    radius_miles: Optional[float] = None
    listing_type: str = "for_sale"
    past_days: Optional[int] = None
    active_only: bool = True  # drop pending/contingent/under-contract listings

    use_realtor: bool = True
    use_redfin: bool = True

    price_min: Optional[int] = None
    price_max: Optional[int] = None
    # "Stretch" band: listings priced above price_max but at or below stretch_price_max are
    # still included if they've sat on the market at least stretch_dom_min days - a seller
    # sitting that long may accept an offer down near price_max. Flagged in the report rather
    # than silently blended in with in-budget listings. Only takes effect if stretch_price_max is set.
    stretch_price_max: Optional[int] = None
    stretch_dom_min: int = 45
    beds_min: Optional[int] = None
    beds_max: Optional[int] = None
    baths_min: Optional[float] = None
    baths_max: Optional[float] = None
    full_baths_min: Optional[int] = None  # stricter than baths_min: excludes half-baths from the count
    sqft_min: Optional[int] = None
    sqft_max: Optional[int] = None
    lot_sqft_min: Optional[int] = None
    lot_sqft_max: Optional[int] = None
    year_built_min: Optional[int] = None
    year_built_max: Optional[int] = None
    property_types: Optional[list[str]] = None
    excluded_property_types: Optional[list[str]] = None  # e.g. ["mobile"] - applied client-side, both sources

    output_dir: str = "reports"
    report_basename: str = "house_report"

    proxy: Optional[str] = None  # e.g. "http://user:pass@host:port" - used by both sources

    @property
    def effective_price_max(self) -> Optional[int]:
        """The ceiling to send to each source's own API - must be at least stretch_price_max,
        or stretch candidates would get filtered out server-side before we ever see them."""
        if self.stretch_price_max is None:
            return self.price_max
        if self.price_max is None:
            return self.stretch_price_max
        return max(self.price_max, self.stretch_price_max)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "SearchCriteria":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        sources = raw.get("sources") or {}

        return cls(
            location=raw["location"],
            radius_miles=raw.get("radius_miles"),
            listing_type=raw.get("listing_type", "for_sale"),
            past_days=raw.get("past_days"),
            active_only=raw.get("active_only", True),
            use_realtor=sources.get("realtor", True),
            use_redfin=sources.get("redfin", True),
            price_min=raw.get("price_min"),
            price_max=raw.get("price_max"),
            stretch_price_max=raw.get("stretch_price_max"),
            stretch_dom_min=raw.get("stretch_dom_min", 45),
            beds_min=raw.get("beds_min"),
            beds_max=raw.get("beds_max"),
            baths_min=raw.get("baths_min"),
            baths_max=raw.get("baths_max"),
            full_baths_min=raw.get("full_baths_min"),
            sqft_min=raw.get("sqft_min"),
            sqft_max=raw.get("sqft_max"),
            lot_sqft_min=raw.get("lot_sqft_min"),
            lot_sqft_max=raw.get("lot_sqft_max"),
            year_built_min=raw.get("year_built_min"),
            year_built_max=raw.get("year_built_max"),
            property_types=raw.get("property_types"),
            excluded_property_types=raw.get("excluded_property_types"),
            output_dir=raw.get("output_dir", "reports"),
            report_basename=raw.get("report_basename", "house_report"),
            proxy=raw.get("proxy"),
        )

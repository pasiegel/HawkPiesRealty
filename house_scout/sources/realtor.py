from __future__ import annotations

import pandas as pd
from homeharvest import scrape_property

from ..config import SearchCriteria


def fetch_realtor(criteria: SearchCriteria) -> pd.DataFrame:
    """Pull listings from realtor.com via HomeHarvest."""
    try:
        df = scrape_property(
            location=criteria.location,
            listing_type=criteria.listing_type,
            radius=criteria.radius_miles,
            past_days=criteria.past_days,
            price_min=criteria.price_min,
            price_max=criteria.effective_price_max,
            beds_min=criteria.beds_min,
            beds_max=criteria.beds_max,
            baths_min=criteria.baths_min,
            baths_max=criteria.baths_max,
            sqft_min=criteria.sqft_min,
            sqft_max=criteria.sqft_max,
            lot_sqft_min=criteria.lot_sqft_min,
            lot_sqft_max=criteria.lot_sqft_max,
            year_built_min=criteria.year_built_min,
            year_built_max=criteria.year_built_max,
            property_type=criteria.property_types,
            extra_property_data=False,
            proxy=criteria.proxy,
            exclude_pending=criteria.active_only,
        )
    except Exception as exc:  # noqa: BLE001 - surface as empty result, caller reports the failure
        print(f"[realtor.com] scrape failed: {exc}")
        return pd.DataFrame()

    return df

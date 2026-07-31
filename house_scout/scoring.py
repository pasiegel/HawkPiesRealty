from __future__ import annotations

import pandas as pd

# Simple, adjustable heuristic - not a market valuation model. It ranks listings
# *relative to the others pulled in the same run*, so it's only meaningful within
# one report, not across separate runs/areas. Tune the weights to taste.
WEIGHT_PRICE_PER_SQFT = 0.6   # cheaper $/sqft than peers = better
WEIGHT_DAYS_ON_MARKET = 0.2   # longer on market = more room to negotiate
WEIGHT_LOT_RATIO = 0.2        # more lot per sqft of house = better


def add_score(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        df["deal_score"] = pd.Series(dtype="float64")
        return df

    df = df.copy()

    # Compute price/sqft ourselves whenever we have the inputs, rather than trusting
    # the source's own field - realtor.com's price_per_sqft is sometimes stale/wrong
    # (e.g. left over from a prior list price), which would otherwise skew the score.
    can_compute = df["list_price"].notna() & df["sqft"].notna() & (df["sqft"] > 0)
    computed_ppsf = df["list_price"] / df["sqft"]
    price_per_sqft = computed_ppsf.where(can_compute, df["price_per_sqft"])
    df["price_per_sqft"] = price_per_sqft.round(2)

    lot_ratio = df["lot_sqft"] / df["sqft"].replace(0, pd.NA)

    # Percentile rank each factor (0-1). Lower price/sqft should score higher, so invert it.
    ppsf_pct = 1 - price_per_sqft.rank(pct=True, ascending=True)
    dom_pct = df["days_on_market"].rank(pct=True, ascending=True)
    lot_pct = lot_ratio.rank(pct=True, ascending=True)

    # Missing values get a neutral 0.5 so they don't drag the score to either extreme.
    ppsf_pct = ppsf_pct.fillna(0.5)
    dom_pct = dom_pct.fillna(0.5)
    lot_pct = lot_pct.fillna(0.5)

    # Expose the per-factor percentiles too (0-100), so a report can explain *why* a
    # listing ranked where it did, not just the blended deal_score.
    df["score_price_per_sqft"] = (100 * ppsf_pct).round(1)
    df["score_days_on_market"] = (100 * dom_pct).round(1)
    df["score_lot_ratio"] = (100 * lot_pct).round(1)

    df["deal_score"] = (
        100
        * (
            WEIGHT_PRICE_PER_SQFT * ppsf_pct
            + WEIGHT_DAYS_ON_MARKET * dom_pct
            + WEIGHT_LOT_RATIO * lot_pct
        )
    ).round(1)

    return df

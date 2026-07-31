from __future__ import annotations

import pandas as pd

# Common schema every source gets mapped into before scoring/merging.
COMMON_COLUMNS = [
    "source",
    "status",
    "address",
    "city",
    "state",
    "zip_code",
    "beds",
    "baths",
    "full_baths",
    "sqft",
    "lot_sqft",
    "year_built",
    "list_price",
    "price_per_sqft",
    "days_on_market",
    "list_date",
    "property_url",
    "latitude",
    "longitude",
    "mls_id",
    "hoa_fee",
    "agent_name",
    "agent_phones",
    "broker_name",
    "style",
    "photo_urls",
]


def normalize_realtor(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=COMMON_COLUMNS)

    out = pd.DataFrame()
    out["source"] = ["realtor.com"] * len(df)
    out["status"] = df.get("status")
    out["address"] = df.get("full_street_line")
    out["city"] = df.get("city")
    out["state"] = df.get("state")
    out["zip_code"] = df.get("zip_code")
    out["beds"] = df.get("beds")
    full_baths = pd.to_numeric(df.get("full_baths"), errors="coerce").fillna(0)
    half_baths = pd.to_numeric(df.get("half_baths"), errors="coerce").fillna(0)
    out["baths"] = full_baths + 0.5 * half_baths
    out["full_baths"] = full_baths
    out["sqft"] = df.get("sqft")
    out["lot_sqft"] = df.get("lot_sqft")
    out["year_built"] = df.get("year_built")
    out["list_price"] = df.get("list_price")
    out["price_per_sqft"] = df.get("price_per_sqft")
    out["days_on_market"] = df.get("days_on_mls")
    out["list_date"] = df.get("list_date")
    out["property_url"] = df.get("property_url")
    out["latitude"] = df.get("latitude")
    out["longitude"] = df.get("longitude")
    out["mls_id"] = df.get("mls_id")
    out["hoa_fee"] = df.get("hoa_fee")
    out["agent_name"] = df.get("agent_name")
    out["agent_phones"] = df.get("agent_phones")
    out["broker_name"] = df.get("broker_name")
    out["style"] = df.get("style")
    # alt_photos is a comma-separated string of CDN URLs; fall back to the single
    # primary_photo when alt_photos is missing so we still get at least one image.
    alt_photos = df.get("alt_photos")
    primary_photo = df.get("primary_photo")
    if alt_photos is not None:
        out["photo_urls"] = alt_photos.where(
            alt_photos.notna() & (alt_photos.astype(str).str.strip() != ""), primary_photo
        )
    else:
        out["photo_urls"] = primary_photo

    return out.reindex(columns=COMMON_COLUMNS)


def normalize_redfin(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=COMMON_COLUMNS)

    out = pd.DataFrame()
    out["source"] = ["redfin"] * len(df)
    out["status"] = df.get("STATUS")
    out["address"] = df.get("ADDRESS")
    out["city"] = df.get("CITY")
    out["state"] = df.get("STATE OR PROVINCE")
    out["zip_code"] = df.get("ZIP OR POSTAL CODE")
    out["beds"] = df.get("BEDS")
    out["baths"] = df.get("BATHS")
    out["full_baths"] = None  # Redfin's CSV export doesn't split full/half baths
    out["sqft"] = df.get("SQUARE FEET")
    out["lot_sqft"] = df.get("LOT SIZE")
    out["year_built"] = df.get("YEAR BUILT")
    out["list_price"] = df.get("PRICE")
    out["price_per_sqft"] = df.get("$/SQUARE FEET")
    out["days_on_market"] = df.get("DAYS ON MARKET")
    out["list_date"] = None
    out["property_url"] = df.get("URL")
    out["latitude"] = df.get("LATITUDE")
    out["longitude"] = df.get("LONGITUDE")
    out["mls_id"] = df.get("MLS#")
    out["hoa_fee"] = df.get("HOA/MONTH")
    out["agent_name"] = None
    out["agent_phones"] = None
    out["broker_name"] = None
    out["style"] = df.get("PROPERTY TYPE")
    # Redfin's CSV export has no photo field; house_scout.photos falls back to
    # scraping the listing page (property_url) for these rows at download time.
    out["photo_urls"] = None

    return out.reindex(columns=COMMON_COLUMNS)

from __future__ import annotations

import io
import time
from typing import Optional

import pandas as pd
import requests

from ..config import SearchCriteria

# Redfin has no official API. This uses the same undocumented "stingray" endpoints
# the redfin.com search page itself calls (location autocomplete + the CSV export
# behind the "Download All" button). Redfin's WAF (CloudFront) blocks requests from
# most cloud/datacenter IP ranges - this generally works from a normal home/residential
# connection but may need a residential proxy when run from a server or hosted app.
# Because it's undocumented, Redfin can change or block it at any time without notice.

BASE = "https://www.redfin.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# uipt = Redfin's internal property-type codes used by search/gis-csv.
UIPT_ALL = "1,2,3,4,5,6,7,8"
PROPERTY_TYPE_MAP = {
    "single_family": "1",
    "condos": "2",
    "townhomes": "3",
    "multi_family": "4",
    "land": "5",
    "other": "6",
    "mobile": "7",
    "coops": "8",
}


def _session(proxy: Optional[str]) -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.redfin.com/",
        }
    )
    if proxy:
        s.proxies.update({"http": proxy, "https": proxy})
    # Warm up cookies like a real browser visit before hitting the API endpoints.
    s.get(BASE, timeout=15)
    return s


def _find_region(session: requests.Session, location: str, debug: bool = False) -> Optional[dict]:
    resp = session.get(
        f"{BASE}/stingray/do/location-autocomplete",
        params={"location": location, "v": 2},
        timeout=15,
    )
    if debug:
        print(f"[redfin] autocomplete GET {resp.url} -> {resp.status_code}")
    resp.raise_for_status()

    text = resp.text
    # Response is prefixed with "{}&&" before the JSON payload.
    if "&&" in text:
        text = text.split("&&", 1)[1]

    import json

    data = json.loads(text)
    sections = data.get("payload", {}).get("sections", [])
    for section in sections:
        for row in section.get("rows", []):
            # Prefer exact city/region matches over individual addresses.
            if row.get("type") in (1, 2, 4, 6):  # city, county, zip, neighborhood
                return row
    for section in sections:
        rows = section.get("rows", [])
        if rows:
            return rows[0]
    return None


def _build_params(criteria: SearchCriteria, region_id: str, region_type: str, page: int) -> dict:
    params = {
        "al": 1,
        "region_id": region_id,
        "region_type": region_type,
        "status": 9,  # active listings
        "uipt": UIPT_ALL,
        "sf": "1,2,3,5,6,7",
        "num_homes": 350,
        "page_number": page,
        "ord": "redfin-recommended-asc",
        "v": 8,
    }

    if criteria.property_types:
        codes = [PROPERTY_TYPE_MAP[p] for p in criteria.property_types if p in PROPERTY_TYPE_MAP]
        if codes:
            params["uipt"] = ",".join(codes)

    if criteria.price_min:
        params["min_price"] = criteria.price_min
    if criteria.effective_price_max:
        params["max_price"] = criteria.effective_price_max
    if criteria.beds_min:
        params["min_beds"] = criteria.beds_min
    if criteria.beds_max:
        params["max_beds"] = criteria.beds_max
    if criteria.baths_min:
        params["min_baths"] = criteria.baths_min
    if criteria.sqft_min:
        params["min_sqft"] = criteria.sqft_min
    if criteria.sqft_max:
        params["max_sqft"] = criteria.sqft_max
    if criteria.lot_sqft_min:
        params["min_lot_size"] = criteria.lot_sqft_min
    if criteria.lot_sqft_max:
        params["max_lot_size"] = criteria.lot_sqft_max
    if criteria.year_built_min:
        params["min_year_built"] = criteria.year_built_min
    if criteria.year_built_max:
        params["max_year_built"] = criteria.year_built_max

    return params


def fetch_redfin(criteria: SearchCriteria, debug: bool = False) -> pd.DataFrame:
    """Pull active listings from Redfin's CSV export endpoint for a given area."""
    try:
        session = _session(criteria.proxy)
        region = _find_region(session, criteria.location, debug=debug)
        if not region:
            print(f"[redfin] could not resolve a region for location '{criteria.location}'")
            return pd.DataFrame()

        region_id = region["id"].split("_")[-1] if "_" in str(region.get("id", "")) else region.get("id")
        region_type = str(region.get("type"))

        frames = []
        page = 1
        while True:
            params = _build_params(criteria, region_id, region_type, page)
            resp = session.get(f"{BASE}/stingray/api/gis-csv", params=params, timeout=20)
            if debug:
                print(f"[redfin] gis-csv GET {resp.url} -> {resp.status_code}")

            if resp.status_code == 403:
                print(
                    "[redfin] request blocked (403). Redfin's WAF often blocks cloud/datacenter "
                    "IPs - try running from a home connection, or set a residential 'proxy' in "
                    "config.yaml. Skipping Redfin for this run."
                )
                break
            resp.raise_for_status()

            if "text/csv" not in resp.headers.get("Content-Type", "") and not resp.text.startswith(
                "SALE TYPE"
            ):
                print("[redfin] unexpected response (likely blocked or endpoint changed); skipping.")
                if debug:
                    print(resp.text[:500])
                break

            page_df = pd.read_csv(io.StringIO(resp.text))
            if page_df.empty:
                break
            frames.append(page_df)

            if len(page_df) < params["num_homes"]:
                break
            page += 1
            time.sleep(1)  # be polite between pages

        if not frames:
            return pd.DataFrame()

        return pd.concat(frames, ignore_index=True)

    except Exception as exc:  # noqa: BLE001 - non-fatal, caller reports the failure
        print(f"[redfin] scrape failed: {exc}")
        return pd.DataFrame()

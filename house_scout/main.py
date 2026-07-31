from __future__ import annotations

import argparse

from .config import SearchCriteria
from .normalize import normalize_realtor, normalize_redfin
from .report import build_report, export_csv
from .sources.realtor import fetch_realtor
from .sources.redfin import fetch_redfin


def run(config_path: str, debug: bool = False) -> None:
    criteria = SearchCriteria.from_yaml(config_path)
    print(f"Searching '{criteria.location}' ({criteria.listing_type}, past_days={criteria.past_days})...")

    frames = []

    if criteria.use_realtor:
        print("Fetching realtor.com listings...")
        realtor_df = fetch_realtor(criteria)
        print(f"  -> {len(realtor_df)} listings")
        frames.append(normalize_realtor(realtor_df))

    if criteria.use_redfin:
        print("Fetching Redfin listings...")
        redfin_df = fetch_redfin(criteria, debug=debug)
        print(f"  -> {len(redfin_df)} listings")
        frames.append(normalize_redfin(redfin_df))

    report = build_report(
        frames,
        full_baths_min=criteria.full_baths_min,
        active_only=criteria.active_only,
        excluded_property_types=criteria.excluded_property_types,
        price_max=criteria.price_max,
        stretch_price_max=criteria.stretch_price_max,
        stretch_dom_min=criteria.stretch_dom_min,
    )
    if report.empty:
        print("No listings found - check your criteria/config.yaml, or that at least one source succeeded.")
        return

    out_path = export_csv(report, criteria.output_dir, criteria.report_basename)
    print(f"\n{len(report)} unique listings -> {out_path}")
    if criteria.stretch_price_max is not None:
        stretch_count = int(report["stretch"].sum())
        print(
            f"({stretch_count} of those are 'stretch' listings over ${criteria.price_max:,.0f} but under "
            f"${criteria.stretch_price_max:,.0f} with {criteria.stretch_dom_min}+ days on market)"
        )
    print("\nTop 10 by deal_score:")
    cols = ["deal_score", "address", "city", "list_price", "price_per_sqft", "beds", "baths", "sqft", "source"]
    print(report[cols].head(10).to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape realtor.com / Redfin listings into a scored CSV report.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml (default: ./config.yaml)")
    parser.add_argument("--debug", action="store_true", help="Print Redfin request URLs/responses for troubleshooting")
    args = parser.parse_args()

    run(args.config, debug=args.debug)


if __name__ == "__main__":
    main()

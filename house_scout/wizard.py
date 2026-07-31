from __future__ import annotations

import sys

import yaml

from .main import run

PROPERTY_TYPE_CHOICES = ["single_family", "condos", "townhomes", "multi_family", "land", "mobile"]


def ask_text(prompt: str, default: str | None = None) -> str | None:
    suffix = f" [{default}]" if default is not None else " (blank to skip)"
    value = input(f"{prompt}{suffix}: ").strip()
    return value if value else default


def ask_int(prompt: str, default: int | None = None) -> int | None:
    while True:
        raw = ask_text(prompt, str(default) if default is not None else None)
        if raw is None or raw == "":
            return None
        try:
            return int(raw)
        except ValueError:
            print("  Please enter a whole number, or leave blank to skip.")


def ask_float(prompt: str, default: float | None = None) -> float | None:
    while True:
        raw = ask_text(prompt, str(default) if default is not None else None)
        if raw is None or raw == "":
            return None
        try:
            return float(raw)
        except ValueError:
            print("  Please enter a number, or leave blank to skip.")


def ask_bool(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{prompt} [{hint}]: ").strip().lower()
        if raw == "":
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  Please answer y or n.")


def ask_choice(prompt: str, choices: list[str], default: str) -> str:
    choice_str = "/".join(c if c != default else c.upper() for c in choices)
    while True:
        raw = input(f"{prompt} ({choice_str}): ").strip().lower()
        if raw == "":
            return default
        if raw in choices:
            return raw
        print(f"  Please pick one of: {', '.join(choices)}")


def ask_multi_choice(prompt: str, choices: list[str]) -> list[str] | None:
    print(f"{prompt}")
    print(f"  Options: {', '.join(choices)}")
    raw = input("  Comma-separated (blank = any type): ").strip().lower()
    if not raw:
        return None
    picked = [p.strip() for p in raw.split(",") if p.strip()]
    invalid = [p for p in picked if p not in choices]
    if invalid:
        print(f"  Ignoring unrecognized type(s): {', '.join(invalid)}")
        picked = [p for p in picked if p in choices]
    return picked or None


def build_config() -> tuple[dict, str]:
    print("House Scout search setup - press Enter to accept the default/skip a filter.\n")

    location = ask_text("Location (city/state, ZIP, or a specific street address)")
    while not location:
        print("  Location is required.")
        location = ask_text("Location (city/state, ZIP, or a specific street address)")

    print(
        "\nRadius is a straight-line distance, not drive time - neither source supports "
        "true drive-time search. Only used when 'location' is a specific address (not a "
        "bare city/ZIP)."
    )
    radius_miles = ask_float("Search radius in miles", default=20)

    listing_type = ask_choice(
        "\nListing type", ["for_sale", "for_rent", "sold", "pending"], default="for_sale"
    )
    past_days = ask_int("Only include listings from the last N days", default=30)
    active_only = ask_bool(
        "Only show active listings (exclude pending/contingent/under contract/sold)?", default=True
    )

    print("\n-- Price --")
    price_min = ask_int("Minimum price", default=None)
    price_max = ask_int("Maximum price", default=None)
    stretch_price_max = None
    stretch_dom_min = 45
    if price_max is not None and ask_bool(
        "Also include pricier listings that have sat on the market a long time "
        "(seller may take less)?",
        default=False,
    ):
        stretch_price_max = ask_int("Stretch price ceiling", default=int(price_max * 1.05))
        stretch_dom_min = ask_int("Minimum days on market to qualify as a stretch listing", default=45)

    print("\n-- Beds / baths --")
    beds_min = ask_int("Minimum bedrooms", default=None)
    beds_max = ask_int("Maximum bedrooms", default=None)
    baths_min = ask_float("Minimum bathrooms (a half-bath counts as 0.5)", default=None)
    baths_max = ask_float("Maximum bathrooms", default=None)
    full_baths_min = ask_int(
        "Minimum FULL bathrooms (stricter - ignores half-baths; realtor.com data only)",
        default=None,
    )

    print("\n-- Size / lot / age --")
    sqft_min = ask_int("Minimum square footage", default=None)
    sqft_max = ask_int("Maximum square footage", default=None)
    lot_sqft_min = ask_int("Minimum lot size (sqft)", default=None)
    lot_sqft_max = ask_int("Maximum lot size (sqft)", default=None)
    year_built_min = ask_int("Minimum year built", default=None)
    year_built_max = ask_int("Maximum year built", default=None)

    print()
    property_types = ask_multi_choice("Property type(s) to INCLUDE", PROPERTY_TYPE_CHOICES)
    excluded_property_types = ask_multi_choice("Property type(s) to EXCLUDE", PROPERTY_TYPE_CHOICES)

    print("\n-- Sources --")
    use_realtor = ask_bool("Include realtor.com?", default=True)
    use_redfin = ask_bool(
        "Include Redfin? (undocumented endpoint - may be blocked on some networks, see README)",
        default=True,
    )
    proxy = ask_text("Proxy URL for Redfin/realtor.com (e.g. http://user:pass@host:port)", default=None)

    print("\n-- Output --")
    output_dir = ask_text("Output folder for CSV reports", default="reports")
    report_basename = ask_text("Report file name prefix", default="house_report")
    config_filename = ask_text("Save this search as", default="config.yaml")

    config = {
        "location": location,
        "radius_miles": radius_miles,
        "listing_type": listing_type,
        "past_days": past_days,
        "active_only": active_only,
        "sources": {"realtor": use_realtor, "redfin": use_redfin},
        "price_min": price_min,
        "price_max": price_max,
        "stretch_price_max": stretch_price_max,
        "stretch_dom_min": stretch_dom_min,
        "beds_min": beds_min,
        "beds_max": beds_max,
        "baths_min": baths_min,
        "baths_max": baths_max,
        "full_baths_min": full_baths_min,
        "sqft_min": sqft_min,
        "sqft_max": sqft_max,
        "lot_sqft_min": lot_sqft_min,
        "lot_sqft_max": lot_sqft_max,
        "year_built_min": year_built_min,
        "year_built_max": year_built_max,
        "property_types": property_types,
        "excluded_property_types": excluded_property_types,
        "output_dir": output_dir,
        "report_basename": report_basename,
        "proxy": proxy,
    }
    return config, config_filename


def main() -> None:
    try:
        config, config_filename = build_config()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        sys.exit(1)

    with open(config_filename, "w", encoding="utf-8") as f:
        f.write("# Generated by house_scout.wizard\n")
        yaml.safe_dump(config, f, sort_keys=False)

    print(f"\nSaved search config to {config_filename}")

    if ask_bool("\nRun this search now?", default=True):
        print()
        run(config_filename)
    else:
        print(f"Run it later with: python -m house_scout.main --config {config_filename}")


if __name__ == "__main__":
    main()

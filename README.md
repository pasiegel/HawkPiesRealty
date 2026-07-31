# House Scout

Scrapes for-sale listings for an area from **realtor.com** (via [HomeHarvest](https://github.com/ZacharyHampton/HomeHarvest)) and **Redfin** (via Redfin's own CSV export endpoint), merges/dedupes them, scores each listing as a relative "deal" within the batch, and exports a single CSV report.

## Why two sources, and why not Zillow

- **realtor.com** — reliable, actively maintained via HomeHarvest.
- **Redfin** — no official API. This uses the same undocumented endpoint the "Download All" button on redfin.com calls. It works fine from a normal home internet connection, but Redfin's WAF blocks most cloud/datacenter IPs outright (confirmed while building this — it returns HTTP 403 from this dev sandbox). If it 403s for you too:
  - Run it from your home machine (most likely fix).
  - Or set `proxy:` in `config.yaml` to a residential proxy.
  - If Redfin changes their endpoint/params, use `--debug` to see the exact request being made and troubleshoot from there. The Redfin fetch fails gracefully — a broken Redfin connector won't stop the realtor.com results from being reported.
- **Zillow** — intentionally not included. Zillow's anti-bot protection is aggressive and there's no reliably maintained open-source scraper for it; anything built would likely break within weeks. Not worth the maintenance burden right now.

## Setup

```bash
cd house_scout
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

## Configure your search

Two ways to set up a search:

- **Interactive wizard** (easiest): `python -m house_scout.wizard` asks about location, radius, price/bed/bath/sqft filters, property types to include/exclude, active-only, and which sources to use, then saves it to a YAML file of your choice and optionally runs it immediately. Handy for building several named searches (e.g. `vegas.yaml`, `grand_rapids.yaml`) without hand-editing YAML.
- **Manual**: edit `config.yaml` directly.

Note on baths: `baths_min` is passed to both sources' APIs and counts a half-bath as 0.5 (so `baths_min: 2` would also match 1 full + 2 half baths). If you specifically need N *full* baths, also set `full_baths_min` — it's applied client-side against realtor.com's full/half split after fetching. Redfin's CSV export doesn't separate full/half baths, so `full_baths_min` can't be checked against Redfin rows; those are kept rather than dropped since we can't evaluate them.

`radius_miles` is a straight-line radius from `location`, not a drive-time radius — neither realtor.com's nor Redfin's search API supports true isochrone/drive-time search. If you want "N minutes from X," approximate it with a mile radius and sanity-check the resulting cities in the report.

`active_only` (default `true`) excludes pending/contingent/under-contract/sold listings, keeping only active for-sale inventory. It's applied two ways: passed to HomeHarvest as `exclude_pending` for realtor.com, and as a client-side status check across both sources' combined results (Redfin's own query already restricts to active listings, so this is mainly a safety net for realtor.com and for anything mislabeled). Set to `false` in `config.yaml` if you want pending/contingent listings included.

`excluded_property_types` (e.g. `["mobile"]`) drops listings by type after fetching, matched against realtor.com's `style` field and Redfin's `PROPERTY TYPE` column by keyword (so it works even though the two sources label types differently). Supported keys: `mobile`, `land`, `farm`, `multi_family` - see `PROPERTY_TYPE_EXCLUSION_MARKERS` in `house_scout/report.py` to add more. This is separate from `property_types`, which is an *include* list passed to realtor.com's own search API.

`stretch_price_max` + `stretch_dom_min`: normally anything over `price_max` is dropped. Set `stretch_price_max` to also keep listings priced between `price_max` and `stretch_price_max`, but only if they've sat on the market at least `stretch_dom_min` days (default 45) — the idea being a seller sitting that long might accept an offer down near your real budget. These aren't silently blended in: `photo_report.py` flags them with an orange "Stretch" badge and a note in both the Markdown and HTML output. Leave `stretch_price_max` as `null` to disable (default).

## Run

If you used the wizard and answered "yes" to running immediately, this already happened. Otherwise:

```bash
python -m house_scout.main
# or point at a different config:
python -m house_scout.main --config my_area.yaml
# troubleshoot Redfin blocking/param issues:
python -m house_scout.main --debug
```

Output: a timestamped CSV in `reports/` (or whatever `output_dir` you set), sorted by `deal_score` descending. The top 10 also print to the console.

## Report columns

| Column | Meaning |
|---|---|
| `deal_score` | 0-100, relative to other listings in *this* run only (not an absolute valuation). Weighted: 60% cheaper $/sqft than peers, 20% longer days on market, 20% larger lot relative to house size. Adjust weights in `house_scout/scoring.py`. |
| `source` | `realtor.com`, `redfin`, or `realtor.com+redfin` if the same address was found on both. |
| `also_listed_at` | URL of the other listing, when a house was found on both sources. |
| `full_baths` | Full-bath count (realtor.com only; blank for Redfin rows). Used by `full_baths_min` filtering. |
| `stretch` / `price_over_budget` | `stretch` is `True` if this listing is over `price_max` but was kept under the `stretch_price_max`/`stretch_dom_min` rule above; `price_over_budget` is how far over. Both blank/`False` if stretch isn't configured. |
| everything else | address, price, beds/baths, sqft, lot size, year built, days on market, agent/broker contact (realtor.com only), lat/long, property URL. |

## Bonus utility: download photos from a single Redfin listing

`redfin_photos.py` is a standalone script (only needs `requests`, not the rest of house_scout) that downloads every photo from one Redfin listing page:

```bash
python redfin_photos.py https://www.redfin.com/TX/Abilene/117-Gulfstream-79602/home/179113145
# custom output folder:
python redfin_photos.py <url> --out my_photos
# troubleshoot if it finds 0 photos (Redfin changed their page structure):
python redfin_photos.py <url> --debug
```

Saves to `redfin_photos/<listing-slug>/001.jpg, 002.jpg, ...`. Like the Redfin search connector, this screen-scrapes an undocumented page structure, so it can break if Redfin changes their markup - `--debug` saves the fetched HTML so you can see what changed.

## Daily automated run (GitHub Actions + Pages)

`.github/workflows/daily-report.yml` runs `inspirada_unicorn.yaml` every day on GitHub's own servers, downloads photos, builds the ranking report, and publishes the HTML slide deck to GitHub Pages — no server of your own needed.

Setup (one-time):

1. Push this repo to GitHub as a **public** repo (Pages needs a public repo unless you're on a paid plan with private Pages).
2. In the repo's **Settings → Pages**, set "Build and deployment" → Source to **GitHub Actions**.
3. That's it — the workflow runs daily at 13:00 UTC (edit the `cron:` line in the workflow file to change the time), and you can also trigger it manually anytime from the **Actions** tab ("Run workflow").
4. Your site publishes to `https://<your-username>.github.io/<repo-name>/` — the slide deck is the homepage, with the CSV (`report.csv`) and full write-up (`ranking_report.md`) linked alongside it.

Each run **replaces** the previous one — there's no accumulating history, so the repo itself stays small (the site content is published as a Pages deployment, not committed to git).

**Redfin will not work from this workflow.** GitHub-hosted runners are cloud/datacenter IPs, which is exactly what Redfin's WAF blocks (see above) — the run will still succeed with realtor.com-only results, same as it does here. To change which search runs daily, edit `inspirada_unicorn.yaml` (or point the workflow at a different config file).

## Known limitations / next steps

- Redfin fragility as noted above — treat it as a bonus source, not the primary one.
- `deal_score` is a simple heuristic (percentile ranking within the pulled batch), not a comp-based valuation. Good for triaging within one report, not for comparing across separate runs/areas.
- No price-history / price-drop tracking yet (Redfin's CSV export doesn't include it; would need per-listing detail page scraping).
- Next phase (not built yet): a Streamlit web form or refreshed notebook for cloud hosting, once you're happy with the criteria/scoring here.

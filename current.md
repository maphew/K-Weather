# Current development state

Last updated: 2026-08-13

## Outcome

K-Weather is intended to retain Riverdale/Whitehorse weather observations and
serve an authenticated, filterable household dashboard available at any time.
Data gathering must run every six hours.

## Completed

- Imported the original Claude handoff and renamed the project K-Weather.
- Corrected the ECCC daily downloader to ignore blank inactive-station rows,
  use the current year dynamically, and prefer Riverdale only when it has
  actual observations.
- Verified the downloader against ECCC: 2,401 valid daily observations from
  2020-01-01 through 2026-08-11, all currently sourced from station 50842
  (`WHITEHORSE A`). Riverdale 1618 and legacy airport 1617 returned no actual
  observations for 2020–2026.
- Chose SQLite and Sprites.dev as the initial application and hosting direction;
  see `ADR/` for rationale.
- Established a public-code/private-operations boundary: account-linked IDs,
  credentials, raw household data, and street-level location stay out of Git.
- Added normalized SQLite stations, observations, and ingestion-run tables.
  ECCC imports upsert on source/station/date/interval/metric, preserve quality
  flags, skip missing measurements, and record completed or failed runs.
- Integrated SQLite persistence into the historical downloader while retaining
  private CSV output for local inspection.
- Added four focused tests for duplicate refreshes, blank placeholder days,
  failed ingestion metadata, and Riverdale-to-airport fallback.
- Added a responsive, read-only Flask dashboard with server-rendered SVG charts
  and linkable date-range, station, and metric filters. The default view shows
  the latest year of high, low, and mean temperature.
- Added dashboard tests for empty, single-series, multiple-metric, and precise
  location privacy states. See ADR 0004 for the rendering decision.

Generated CSV files under `yukon_weather/` are local verification output and
are intentionally ignored by Git. The private SQLite database is ignored too.
There is no authentication, scheduler, or deployment configuration yet.

The sanitized history is published in the public `maphew/K-Weather` GitHub
repository. The imported private handoff history was intentionally excluded.
`main` tracks `origin/main`.

## Next job

Add the protected operational boundary:

1. Require application-level authentication configured only through secrets.
2. Add an authenticated, idempotent refresh endpoint or command that updates
   ECCC data without re-fetching every historical year.
3. Record refresh freshness and failures visibly without exposing internals.
4. Test unauthorized access, refresh retries, and concurrent requests.

After this boundary is tested, deploy to Sprites.dev and configure the external
six-hour trigger.

## Verification

- `python -m unittest -v`: 8 tests passed.
- Live ECCC import: 2,401 daily rows became 14,066 normalized observations
  spanning 2020-01-01 through 2026-08-11.
- Reimporting all 2,401 rows left the observation count at 14,066, confirming
  idempotency on real data.
- Browser exercise on real data: default view rendered three charts; submitting
  a mean-temperature/date filter produced one chart and preserved all filters
  in the URL. The inspected desktop screenshot had no clipping or layout defects.

## Time-sensitive manual action

Export the current rolling 31-day MyAcuRite CSV before older readings expire.
MyAcuRite does not retain older detailed observations.

## Session rule

Update this file before ending any development session when the completed work,
test evidence, blocker, or immediate next job has changed. Record durable
architectural decisions separately in `ADR/` and link them here when relevant.

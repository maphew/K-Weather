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

Generated CSV files under `yukon_weather/` are local verification output and
are intentionally ignored by Git. There is no dashboard, database, scheduler,
or deployment configuration yet.

The sanitized history is published in the public `maphew/K-Weather` GitHub
repository. The imported private handoff history was intentionally excluded.
`main` tracks `origin/main`.

## Next job

Build the normalized SQLite ingestion layer:

1. Define stations, observations, and ingestion-run metadata.
2. Make ECCC refreshes idempotent using a unique source/station/timestamp/metric
   identity (or an equivalently safe normalized key).
3. Import the existing daily ECCC response into SQLite without storing blank
   placeholder days.
4. Add focused tests for duplicate refreshes, station fallback, and missing
   observations.

Do not start the dashboard until this persistence contract is tested.

## Time-sensitive manual action

Export the current rolling 31-day MyAcuRite CSV before older readings expire.
MyAcuRite does not retain older detailed observations.

## Session rule

Update this file before ending any development session when the completed work,
test evidence, blocker, or immediate next job has changed. Record durable
architectural decisions separately in `ADR/` and link them here when relevant.

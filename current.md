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
- Added a mobile-friendly login form with secret-configured signed session
  cookies and security headers that prevent caching, framing, and referrer
  leakage. Browser-native Basic Auth remains available only as a compatibility
  path for scripted checks.
- Added an incremental single-writer refresh endpoint. It downloads only the
  current ECCC year (plus the previous year in January), records batch status,
  rejects overlapping requests, and shows only a generic failure notice.
- Added GitHub Actions scheduling at minute 17 every six hours. It authenticates
  with a short-lived GitHub OIDC token bound to this repository and workflow;
  no long-lived scheduler secret exists. See ADR 0005.
- Deployed production to Sprites.dev with one Gunicorn worker, persistent
  SQLite storage, a restart-on-wake Sprite Service, and app authentication.
- Replaced browser-native authentication prompts with a mobile-friendly sign-in
  form after Android Firefox and Chrome repeatedly rejected the popup flow.
- Rotated the dashboard password again and added a separate signed-session key.
- Made username matching case-insensitive, trimmed accidental copy whitespace,
  disabled mobile autocapitalization/correction, and rotated to an alphanumeric-
  only password after a second Android login report.
- Created Sprite checkpoint `v4` after the Android login hardening.
- Added a privacy-preserving MyAcuRite cloud client for the AcuRite Iris. It
  signs in with private environment configuration, retries one expired session,
  normalizes the latest sensor snapshot, discards precise location metadata,
  and emits only sanitized errors. See ADR 0006.
- Integrated optional household capture into the existing protected six-hour
  refresh and normalized SQLite store. Snapshot check-in timestamps make
  retries idempotent, and the household station and metrics now work with the
  dashboard's date, station, and metric filters.
- Updated chart queries for sub-daily timestamps and inclusive end dates.
- Verified the private API against the household account without retaining raw
  responses: automatic discovery found one hub and the Iris returned nine
  usable readings in the expected metric units. The hardware Device ID is not
  needed and was removed from configuration.
- Deployed the integration and private credentials to the Sprite, completed a
  protected production refresh, and verified nine recent AcuRite observations
  and the authenticated household dashboard without exposing coordinates.
- Created Sprite checkpoint `v5` after production verification.
- Added an at-a-glance current-conditions section matching MyAcuRite's
  instrument-generated statistics without copying its design. It covers all
  Iris readings and both linked auxiliary sensors, formats wind bearing as a
  compass direction, and retains the historical filters below. See ADR 0007.
- Expanded six-hour ingestion from the Iris alone to every linked household
  sensor while continuing to discard upstream IDs and exact location fields.
- Deployed and verified three production current-condition cards with 17 total
  readings. Desktop and 390 px browser checks found no clipped values or
  horizontal overflow. The dashboard flags the Iris as stale because MyAcuRite
  reports an older check-in than the two current auxiliary sensors.
- Added a tooltip to the stale indicator explaining that it means MyAcuRite has
  not reported a new reading for more than 12 hours.
- Added synchronized From/To sliders for the historical range while preserving
  editable dates and no-JavaScript GET behavior. The shared range applies to
  every selected source; AcuRite temperature is now in the default history and
  sparse household samples render as visible points. See ADR 0008.

Generated CSV files under `yukon_weather/` are local verification output and
are intentionally ignored by Git. The private SQLite database is ignored too.
Production credentials live only in the ignored local `.env` and Sprite service
environment. Never copy their values into this file, Git, logs, or issues.

The sanitized history is published in the public `maphew/K-Weather` GitHub
repository. The imported private handoff history was intentionally excluded.

## Next job

Preserve the history that predates automated capture:

1. Export and privately attach the current rolling 31-day MyAcuRite CSV before
   older readings expire. Inspect its real schema, then add the importer.
2. After enough snapshots accumulate, consider household-vs-ECCC calibration
   comparisons. Direct Acuparse capture remains the fallback for finer detail.

## Production

- URL: `https://k-weather-m4xy.sprites.app`
- Sprite: organization `matt-wilkie`, Sprite `k-weather`
- Service: `dashboard`, one Gunicorn worker on port 8080
- Database: `/home/sprite/k-weather/yukon_weather/k-weather.sqlite3`
- Schedule: `.github/workflows/refresh.yml`, `17 */6 * * *`
- Checkpoint: `v6`

For a code update: push `main`, run `sprite exec -- bash -lc 'cd
/home/sprite/k-weather && git pull --ff-only && .venv/bin/pip install -r
requirements.txt'`, then restart the `dashboard` Sprite Service. Preserve the
database and service environment.

## Verification

- `python -m unittest -v`: 31 tests passed, including MyAcuRite login/session
  retry, schema validation, null readings, timestamp/unit normalization,
  privacy-safe failures, idempotent snapshots, sub-daily dashboard filtering,
  form login sessions, OIDC claims, refresh failure recording, and concurrency.
- Ruff lint and formatting checks passed for all tracked Python.
- Live ECCC import: 2,401 daily rows became 14,066 normalized observations
  spanning 2020-01-01 through 2026-08-11.
- Reimporting all 2,401 rows left the observation count at 14,066, confirming
  idempotency on real data.
- Browser exercise on real data: default view rendered three charts; submitting
  a mean-temperature/date filter produced one chart and preserved all filters
  in the URL. The inspected desktop screenshot had no clipping or layout defects.
- Production redirects unauthenticated dashboard visits to `/login`; a random
  refresh bearer token returns `401`.
- GitHub Actions workflow runs `31664609923`, `31664825519`, and `31667596567`
  obtained OIDC tokens and completed protected production refreshes
  successfully, including after the mobile login deployment.
- Production SQLite remained at 14,066 unique observations and recorded one
  completed refresh per workflow run. The authenticated 390 px browser check
  rendered three charts with no horizontal overflow.
- A second 390 px production browser check exercised the normal login form with
  the final rotated credentials, loaded all three charts, and verified that the
  resulting session cookie is both `Secure` and `HttpOnly`.
- The exact final credential artifact was parsed and submitted to the production
  form: login returned `302` to the dashboard and the resulting session loaded
  the dashboard with HTTP `200`.
- Live MyAcuRite verification discovered one hub and selected the Iris
  (`5in1WS`) from three devices. It returned nine usable readings: temperature,
  humidity, wind speed/direction/average, feels-like temperature, dew point,
  pressure, and rainfall, in the expected Canadian units.
- GitHub Actions workflow run `31723254276` completed the first protected
  production AcuRite refresh successfully. Production stored exactly nine
  household observations with no external ID or coordinates; an authenticated
  dashboard request rendered the AcuRite temperature chart and safe Riverdale
  station label.
- Workflow run `31724056172` captured all three household devices. Production
  now exposes nine Iris readings plus four readings from each auxiliary sensor.
  Automated DOM checks confirmed three cards, 17 values, no coordinates or
  account-linked station metadata, and no horizontal overflow at desktop or
  390 px widths. Inspected screenshots confirmed all values are readable.

## Time-sensitive manual action

Export the current rolling 31-day MyAcuRite CSV before older readings expire.
MyAcuRite does not retain older detailed observations.

## Session rule

Update this file before ending any development session when the completed work,
test evidence, blocker, or immediate next job has changed. Record durable
architectural decisions separately in `ADR/` and link them here when relevant.

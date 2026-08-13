# K-Weather

Persistent weather history and a family-friendly dashboard for Riverdale,
Whitehorse, YT. Two sources, two time horizons.

## Context

The household has an **AcuRite Iris** weather station. The goal is to own the
data locally and analyse it without publishing account-linked identifiers or a
street-level location.

Two findings that shaped this:

1. **MyAcuRite retains only 31 days.** The `/timespans/alltime` and
   `/timespans/year` URL fragments are client-side routing only — the backend
   has nothing older. Anything before ~31 days ago is permanently gone. The
   page itself admits this: *"Charting is only available for up to the previous
   31 days."*
2. **So historical context has to come from Environment Canada**, and
   go-forward AcuRite data has to be captured locally before it rolls off.

## Current state

- `get_yukon_weather.py` — pulls ECCC **daily** data from 2020 through the
  current year.
  Runnable as-is: `uv run get_yukon_weather.py`. Writes to `./yukon_weather/`.
- Live endpoint verification on 2026-08-13 confirmed that station 50842 has
  current observations. Stations 1618 and 1617 respond but currently contain
  blank calendar rows; the script now discards those placeholders.
- `weather_store.py` owns the normalized SQLite schema and idempotent ECCC
  ingestion. The downloader writes private runtime data to
  `yukon_weather/k-weather.sqlite3`.
- `test_weather_store.py` covers duplicate refreshes, blank observations,
  failed-run metadata, and station fallback.
- `app.py`, `dashboard.py`, and `templates/dashboard.html` provide the
  read-only Flask dashboard with server-rendered SVG charts and linkable date,
  station, and metric filters. See ADR 0004.
- `test_dashboard.py` covers empty, single-series, multi-metric, and location
  privacy states.
- Dashboard access uses secret-configured HTTP Basic authentication. Scheduled
  refresh uses a repository/workflow-bound GitHub Actions OIDC token; no static
  scheduler credential is stored. Refresh is incremental, single-writer, and
  recorded in `refresh_runs`. See ADR 0005.
- `.github/workflows/refresh.yml` triggers refresh at minute 17 every six hours.

## Stations

| Key | Name | ECCC station ID | Notes |
|---|---|---|---|
| `riverdale` | WHITEHORSE RIVERDALE | 1618 | Climate ID 2101400. Co-op site; current daily responses are blank. Preferred when observations exist. |
| `whitehorse_a` | WHITEHORSE A | 50842 | Climate ID 2101303. Current airport station and active fallback. |
| `whitehorse_a_legacy` | WHITEHORSE A | 1617 | Climate ID 2101300. Legacy airport record. |

Station IDs are ECCC's *internal* numeric IDs, not the 7-digit Climate ID.
Verify at <https://climate.weather.gc.ca/historical_data/search_historic_data_e.html>.

## ECCC bulk endpoint

```
https://climate.weather.gc.ca/climate_data/bulk_data_e.html
  ?format=csv
  &stationID=<internal ID>
  &Year=<YYYY>&Month=1&Day=1
  &timeframe=2          # 1=hourly, 2=daily, 3=monthly
  &submit=Download+Data
```

One year per request for daily; one *month* per request for hourly
(`timeframe=1` ignores nothing but returns a single month — `Month` matters
there). Public, no auth, no documented rate limit — script sleeps 1s anyway.

Licence: Open Government Licence – Canada. Free to redistribute.

## Product direction

The desired product is an always-addressable dashboard that a non-technical
family member can browse and filter. Weather data should refresh every six
hours and remain queryable indefinitely.

Prefer a small Python web app with SQLite as the first implementation. Keep
ingestion idempotent with a unique key based on source, station, timestamp,
and observation type so scheduled refreshes can safely overlap.

Target **Sprites.dev** first:

- Its persistent filesystem suits a single-node SQLite app.
- A Sprite URL wakes the service on demand, and a Sprite Service restarts the
  dashboard after hibernation.
- Hibernation stops processes, so an in-process scheduler alone cannot
  guarantee six-hour refreshes. Use an external scheduler to call a protected,
  idempotent refresh endpoint every six hours.
- Sprite URLs are private by default. If made public for family access, add
  application authentication; do not rely on the URL being hard to guess.

**Fly.io** is the fallback if conventional production operations matter more
than minimal setup. Use one web Machine, a persistent volume for SQLite, and
Supercronic or Cron Manager for the six-hour job. Do not run multiple writers
against a single SQLite volume.

## Resume order

1. Run and inspect the corrected historical importer.
2. Define a normalized SQLite schema and idempotent ECCC upsert.
3. Add the read-only dashboard with date, station/source, and metric filters.
4. Add a protected refresh command/endpoint and six-hour scheduling.
5. Import the manually exported current MyAcuRite CSV.
6. Deploy to a Sprite with app-level authentication; evaluate Fly.io only if
   Sprite scheduling or operations prove awkward.
7. Separately stand up **Acuparse** (<https://docs.acuparse.com/>) on private
   household infrastructure for direct AcuRite capture. It captures forward
   only and does not replace exporting the current rolling 31-day MyAcuRite
   window now.

## Conventions

Lazy repo — minimal README, no CI, no test suite unless something earns one.
Script is uv-inline-metadata style, single file, stdlib + requests + pandas.

`current.md` is the cold-start handoff and the first file a new development
session should read. Update it whenever completed work, verification evidence,
the immediate next job, or a material blocker changes. Keep it concise and
current; durable architectural decisions and their rationale belong in `ADR/`.

This repository is public. Follow `ADR/0003-public-code-private-operations.md`:
never commit credentials, account-linked device/hub IDs, raw household weather
exports, databases, or street-level location data. Public UI copy may identify
the location as Riverdale, Whitehorse, but no more precisely. Secrets belong in
local environment files or hosting secret stores, not obfuscated in source.

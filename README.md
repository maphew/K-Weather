# K-Weather

K-Weather will collect long-term weather observations for Riverdale,
Whitehorse, and expose them in a filterable dashboard for family use.

This public repository contains application code only. Household station data,
account identifiers, credentials, and precise location details remain private.

The imported first step downloads Environment and Climate Change Canada daily
observations from 2020 through the current year, preferring the Riverdale
station when it has real observations and otherwise using Whitehorse Airport.

## Run the importer

With [uv](https://docs.astral.sh/uv/):

```bash
uv run get_yukon_weather.py
```

The importer writes normalized observations to
`yukon_weather/k-weather.sqlite3`. It also keeps CSV exports under
`yukon_weather/` for local inspection. The database and exports are private
runtime data and intentionally ignored by Git.

Run the focused persistence tests with:

```bash
uv run --with flask --with pandas --with requests python -m unittest -v
```

## Run the dashboard

After importing observations, start the local dashboard on port 8080:

```bash
uv run app.py
```

Set `K_WEATHER_DB` to use a database outside the default
`yukon_weather/k-weather.sqlite3` path. The dashboard opens SQLite in read-only
mode and supports linkable date, station, and metric filters.

The deployed app requires `K_WEATHER_USERNAME` and `K_WEATHER_PASSWORD`; it
returns an error rather than opening the dashboard when they are absent.
`POST /refresh` accepts only the signed, short-lived GitHub Actions OIDC token
from this repository's refresh workflow. An optional local
`K_WEATHER_REFRESH_TOKEN` can be used for manual testing but is not needed in
production. See `.env.example` for variable names—never commit real values.

The refresh workflow runs at minute 17 every six hours. It downloads only the
current year (plus the previous year during January), safely upserts repeated
observations, and wakes the Sprite through its public URL. The dashboard itself
remains protected by application authentication.

Read `current.md` first when resuming development. See `AGENTS.md` for source
details and project conventions, and `ADR/` for durable decision history.

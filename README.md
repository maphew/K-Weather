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
uv run --with pandas --with requests python -m unittest -v
```

Read `current.md` first when resuming development. See `AGENTS.md` for source
details and project conventions, and `ADR/` for durable decision history.

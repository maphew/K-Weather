#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "pandas"]
# ///
"""Pull daily climate data from Environment & Climate Change Canada for
Whitehorse stations (Riverdale + nearby fallbacks).

Usage:
    uv run get_yukon_weather.py
    # or, if you don't have uv:
    pip install requests pandas && python get_yukon_weather.py

Output: normalized observations in ./yukon_weather/k-weather.sqlite3,
./yukon_weather/<station>_daily_<start>-<end>.csv per station, and a merged
./yukon_weather/whitehorse_merged_daily.csv preferring Riverdale and filling
gaps from the current airport station.

The ECCC bulk endpoint:
    https://climate.weather.gc.ca/climate_data/bulk_data_e.html
        ?format=csv&stationID=<ID>&Year=<YYYY>&Month=1&Day=1
        &timeframe=2&submit=Download+Data
    timeframe: 1=hourly, 2=daily, 3=monthly
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from weather_store import connect_database, ingest_eccc_daily

BASE_URL = "https://climate.weather.gc.ca/climate_data/bulk_data_e.html"

# Station IDs are ECCC's internal numeric IDs (not the 7-digit Climate ID).
# Verify any of these at:
#   https://climate.weather.gc.ca/historical_data/search_historic_data_e.html
STATIONS: dict[str, int] = {
    "riverdale": 1618,  # WHITEHORSE RIVERDALE  (Climate ID 2101400)
    "whitehorse_a_legacy": 1617,  # WHITEHORSE A      (legacy airport ID)
    "whitehorse_a": 50842,  # WHITEHORSE A           (current airport station)
}

START_YEAR = 2020
END_YEAR = datetime.now(timezone.utc).year  # inclusive; partial OK for current year

OUTDIR = Path("yukon_weather")
DATABASE = OUTDIR / "k-weather.sqlite3"
SLEEP_SEC = 1.0  # be polite to a public gov endpoint

OBSERVATION_COLUMNS = (
    "Max Temp (°C)",
    "Min Temp (°C)",
    "Mean Temp (°C)",
    "Heat Deg Days (°C)",
    "Cool Deg Days (°C)",
    "Total Rain (mm)",
    "Total Snow (cm)",
    "Total Precip (mm)",
    "Snow on Grnd (cm)",
    "Dir of Max Gust (10s deg)",
    "Spd of Max Gust (km/h)",
)

# ---------------------------------------------------------------------------


def fetch_year(station_id: int, year: int) -> pd.DataFrame:
    """Fetch one year of daily data. Returns empty DataFrame on no data."""
    params = {
        "format": "csv",
        "stationID": station_id,
        "Year": year,
        "Month": 1,
        "Day": 1,
        "timeframe": 2,  # daily
        "submit": "Download Data",
    }
    r = requests.get(BASE_URL, params=params, timeout=60)
    r.raise_for_status()
    text = r.text
    if not text.strip() or "Date/Time" not in text:
        return pd.DataFrame()
    df = pd.read_csv(StringIO(text))
    # Inactive stations still return one row per calendar day, but all weather
    # values are blank. Do not let those placeholders mask a working fallback.
    if df.empty or df.dropna(how="all").empty:
        return pd.DataFrame()
    observation_columns = [column for column in OBSERVATION_COLUMNS if column in df]
    if not observation_columns:
        return pd.DataFrame()
    return df.dropna(subset=observation_columns, how="all").reset_index(drop=True)


def pull_station(name: str, station_id: int) -> pd.DataFrame:
    print(f"\n=== {name} (station {station_id}) ===", flush=True)
    chunks: list[pd.DataFrame] = []
    for y in range(START_YEAR, END_YEAR + 1):
        try:
            df = fetch_year(station_id, y)
        except (requests.RequestException, pd.errors.ParserError) as e:
            print(f"  {y}: FAILED  {e}", flush=True)
            time.sleep(SLEEP_SEC)
            continue
        if df.empty:
            print(f"  {y}: no data", flush=True)
        else:
            chunks.append(df)
            print(f"  {y}: {len(df):4d} rows", flush=True)
        time.sleep(SLEEP_SEC)
    return pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()


def merge_preferring_riverdale(per_station: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build a daily series, preferring Riverdale then current/legacy airport."""
    order = ["riverdale", "whitehorse_a", "whitehorse_a_legacy"]
    frames = [
        per_station[k].assign(_source=k)
        for k in order
        if not per_station.get(k, pd.DataFrame()).empty
    ]
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames, ignore_index=True)
    # Date/Time is the daily date column
    merged["Date/Time"] = pd.to_datetime(merged["Date/Time"], errors="coerce")
    merged = merged.dropna(subset=["Date/Time"])
    # Source priority: lower index in `order` = higher priority
    priority = {k: i for i, k in enumerate(order)}
    merged["_prio"] = merged["_source"].map(priority)
    merged = merged.sort_values(["Date/Time", "_prio"]).drop_duplicates(
        subset=["Date/Time"], keep="first"
    )
    merged = (
        merged.drop(columns=["_prio"]).sort_values("Date/Time").reset_index(drop=True)
    )
    return merged


def main() -> int:
    OUTDIR.mkdir(exist_ok=True)
    database = connect_database(DATABASE)
    per_station: dict[str, pd.DataFrame] = {}
    try:
        for name, sid in STATIONS.items():
            df = pull_station(name, sid)
            per_station[name] = df
            result = ingest_eccc_daily(
                database,
                station_key=name,
                station_id=sid,
                rows=df.to_dict(orient="records"),
            )
            print(
                f"  stored {result.observations_written} observations in {DATABASE}",
                flush=True,
            )
            if df.empty:
                continue
            path = OUTDIR / f"{name}_daily_{START_YEAR}-{END_YEAR}.csv"
            df.to_csv(path, index=False)
            print(f"  wrote {path}  ({len(df)} rows)", flush=True)
    finally:
        database.close()

    merged = merge_preferring_riverdale(per_station)
    if not merged.empty:
        path = OUTDIR / "whitehorse_merged_daily.csv"
        merged.to_csv(path, index=False)
        print(f"\nMerged daily series: {path}  ({len(merged)} rows)")
        print("Source breakdown:")
        print(merged["_source"].value_counts().to_string())
    else:
        print(
            "\nNo data retrieved from any station. "
            "Check the station IDs at climate.weather.gc.ca.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

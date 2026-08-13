"""Import a private MyAcuRite rolling-history CSV into K-Weather."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from myacurite import SensorReading, station_name
from weather_store import IngestionResult, ingest_myacurite_history

CSV_METRICS = {
    "Temperature ( C )": ("temperature", "°C"),
    "Humidity ( RH )": ("humidity", "%RH"),
    "Dew Point ( C )": ("dew_point", "°C"),
    "Heat Index ( C )": ("heat_index", "°C"),
    "Feels Like ( C )": ("feels_like", "°C"),
    "Wind Chill ( C )": ("wind_chill", "°C"),
    "Barometric Pressure ( HPA )": ("pressure", "hPa"),
    "Accumulated Rain ( MM )": ("rainfall", "mm"),
    "Wind Speed ( KPH )": ("wind_speed", "km/h"),
    "Wind Average ( KPH )": ("wind_speed_average", "km/h"),
    "Wind Direction": ("wind_direction", ""),
    "Wired Sensor Temperature": ("wired_sensor_temperature", "°C"),
    "Wired Sensor Humidity": ("wired_sensor_humidity", "%RH"),
    "Soil & Liquid Temperature": ("soil_liquid_temperature", "°C"),
    "Water Detected": ("water_detected", ""),
    "UV Index": ("uv_index", ""),
    "Light Intensity": ("light_intensity", "lx"),
    "Measured Light": ("measured_light", ""),
    "Lightning Strike Count": ("lightning_strike_count", ""),
    "Lightning Closest Strike Distance": (
        "lightning_closest_strike_distance",
        "km",
    ),
}


@dataclass(frozen=True)
class HistoryRow:
    station_key: str
    station_name: str
    observed_at: str
    readings: tuple[SensorReading, ...]


def normalize_csv_timestamp(value: str) -> str:
    parsed = datetime.strptime(value.strip(), "%Y/%m/%d %I:%M %p").replace(
        tzinfo=ZoneInfo("America/Whitehorse")
    )
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def station_keys(connection: sqlite3.Connection) -> dict[str, str]:
    return {
        name.casefold(): key
        for key, name in connection.execute(
            "SELECT station_key, name FROM stations WHERE source = 'myacurite'"
        )
    }


def parse_csv(
    connection: sqlite3.Connection, path: str | Path
) -> tuple[HistoryRow, ...]:
    known_stations = station_keys(connection)
    records = []
    with Path(path).open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        missing = {"Sensor Name", "Sensor Type", "Timestamp"}.difference(
            reader.fieldnames or ()
        )
        if missing:
            raise ValueError("MyAcuRite CSV is missing required columns")
        for row in reader:
            display_name = station_name(row["Sensor Name"], "Household sensor")
            if row["Sensor Type"] == "AcuRite Iris®":
                key = "home"
            else:
                key = known_stations.get(display_name.casefold())
                if key is None:
                    raise ValueError(
                        "MyAcuRite CSV sensor does not match a configured station"
                    )
            readings = tuple(
                SensorReading(metric, float(row[column]), unit)
                for column, (metric, unit) in CSV_METRICS.items()
                if row.get(column, "").strip()
            )
            if readings:
                records.append(
                    HistoryRow(
                        station_key=key,
                        station_name=display_name,
                        observed_at=normalize_csv_timestamp(row["Timestamp"]),
                        readings=readings,
                    )
                )
    return tuple(records)


def import_csv(connection: sqlite3.Connection, path: str | Path) -> IngestionResult:
    return ingest_myacurite_history(connection, rows=parse_csv(connection, path))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("--database", default="yukon_weather/k-weather.sqlite3")
    args = parser.parse_args()
    connection = sqlite3.connect(args.database)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        result = import_csv(connection, args.csv)
    finally:
        connection.close()
    print(
        f"Imported {result.rows_received} rows and "
        f"{result.observations_written} observations"
    )


if __name__ == "__main__":
    main()

"""SQLite persistence for normalized K-Weather observations."""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ECCC_METRICS = {
    "Max Temp (°C)": ("maximum_temperature", "°C", "Max Temp Flag"),
    "Min Temp (°C)": ("minimum_temperature", "°C", "Min Temp Flag"),
    "Mean Temp (°C)": ("mean_temperature", "°C", "Mean Temp Flag"),
    "Heat Deg Days (°C)": ("heating_degree_days", "°C", "Heat Deg Days Flag"),
    "Cool Deg Days (°C)": ("cooling_degree_days", "°C", "Cool Deg Days Flag"),
    "Total Rain (mm)": ("rain", "mm", "Total Rain Flag"),
    "Total Snow (cm)": ("snow", "cm", "Total Snow Flag"),
    "Total Precip (mm)": ("precipitation", "mm", "Total Precip Flag"),
    "Snow on Grnd (cm)": ("snow_on_ground", "cm", "Snow on Grnd Flag"),
    "Dir of Max Gust (10s deg)": (
        "maximum_gust_direction",
        "10s deg",
        "Dir of Max Gust Flag",
    ),
    "Spd of Max Gust (km/h)": (
        "maximum_gust_speed",
        "km/h",
        "Spd of Max Gust Flag",
    ),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS stations (
    source TEXT NOT NULL,
    station_key TEXT NOT NULL,
    external_id TEXT,
    name TEXT NOT NULL,
    climate_id TEXT,
    PRIMARY KEY (source, station_key)
);

CREATE TABLE IF NOT EXISTS observations (
    source TEXT NOT NULL,
    station_key TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    interval TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    quality_flag TEXT,
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (source, station_key, observed_at, interval, metric),
    FOREIGN KEY (source, station_key) REFERENCES stations (source, station_key)
);

CREATE INDEX IF NOT EXISTS observations_filter
ON observations (observed_at, metric, source, station_key);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    station_key TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    rows_received INTEGER NOT NULL DEFAULT 0,
    observations_written INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    FOREIGN KEY (source, station_key) REFERENCES stations (source, station_key)
);

CREATE TABLE IF NOT EXISTS refresh_runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    stations INTEGER NOT NULL DEFAULT 0,
    observations_written INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
"""


@dataclass(frozen=True)
class IngestionResult:
    run_id: int
    rows_received: int
    observations_written: int


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect_database(path: str | Path) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(SCHEMA)
    return connection


def is_missing(value: Any) -> bool:
    if value is None or value == "":
        return True
    return isinstance(value, float) and math.isnan(value)


def normalize_date(value: Any) -> str:
    if is_missing(value):
        raise ValueError("ECCC row has no Date/Time")
    parsed = datetime.fromisoformat(str(value).strip())
    return parsed.date().isoformat()


def ingest_eccc_daily(
    connection: sqlite3.Connection,
    *,
    station_key: str,
    station_id: int,
    rows: Iterable[Mapping[str, Any]],
) -> IngestionResult:
    records = list(rows)
    metadata = next(iter(records), {})
    station_name = metadata.get("Station Name") or station_key
    climate_id = metadata.get("Climate ID")
    started_at = utc_now()

    with connection:
        connection.execute(
            """
            INSERT INTO stations (source, station_key, external_id, name, climate_id)
            VALUES ('eccc', ?, ?, ?, ?)
            ON CONFLICT (source, station_key) DO UPDATE SET
                external_id = excluded.external_id,
                name = excluded.name,
                climate_id = excluded.climate_id
            """,
            (station_key, str(station_id), str(station_name), climate_id),
        )
        cursor = connection.execute(
            """
            INSERT INTO ingestion_runs
                (source, station_key, started_at, status, rows_received)
            VALUES ('eccc', ?, ?, 'running', ?)
            """,
            (station_key, started_at, len(records)),
        )
        run_id = cursor.lastrowid

    observations_written = 0
    try:
        with connection:
            for row in records:
                observed_at = normalize_date(row.get("Date/Time"))
                for column, (metric, unit, flag_column) in ECCC_METRICS.items():
                    value = row.get(column)
                    if is_missing(value):
                        continue
                    flag = row.get(flag_column)
                    connection.execute(
                        """
                        INSERT INTO observations
                            (source, station_key, observed_at, interval, metric,
                             value, unit, quality_flag, ingested_at)
                        VALUES ('eccc', ?, ?, 'daily', ?, ?, ?, ?, ?)
                        ON CONFLICT
                            (source, station_key, observed_at, interval, metric)
                        DO UPDATE SET
                            value = excluded.value,
                            unit = excluded.unit,
                            quality_flag = excluded.quality_flag,
                            ingested_at = excluded.ingested_at
                        """,
                        (
                            station_key,
                            observed_at,
                            metric,
                            float(value),
                            unit,
                            None if is_missing(flag) else str(flag),
                            started_at,
                        ),
                    )
                    observations_written += 1
            connection.execute(
                """
                UPDATE ingestion_runs
                SET completed_at = ?, status = 'completed', observations_written = ?
                WHERE id = ?
                """,
                (utc_now(), observations_written, run_id),
            )
    except Exception as error:
        with connection:
            connection.execute(
                """
                UPDATE ingestion_runs
                SET completed_at = ?, status = 'failed', error = ?
                WHERE id = ?
                """,
                (utc_now(), str(error), run_id),
            )
        raise

    return IngestionResult(run_id, len(records), observations_written)


def ingest_myacurite_snapshot(
    connection: sqlite3.Connection,
    *,
    station_key: str = "home",
    station_name: str = "Riverdale household station",
    observed_at: str,
    readings: Iterable[Any],
) -> IngestionResult:
    """Idempotently store one household snapshot without account identifiers."""
    records = list(readings)
    started_at = utc_now()
    with connection:
        connection.execute(
            """
            INSERT INTO stations (source, station_key, name)
            VALUES ('myacurite', ?, ?)
            ON CONFLICT (source, station_key) DO UPDATE SET name = excluded.name
            """,
            (station_key, station_name),
        )
        run_id = connection.execute(
            """
            INSERT INTO ingestion_runs
                (source, station_key, started_at, status, rows_received)
            VALUES ('myacurite', ?, ?, 'running', ?)
            """,
            (station_key, started_at, len(records)),
        ).lastrowid

    try:
        with connection:
            for reading in records:
                connection.execute(
                    """
                    INSERT INTO observations
                        (source, station_key, observed_at, interval, metric,
                         value, unit, quality_flag, ingested_at)
                    VALUES ('myacurite', ?, ?, 'snapshot', ?, ?, ?, NULL, ?)
                    ON CONFLICT
                        (source, station_key, observed_at, interval, metric)
                    DO UPDATE SET value = excluded.value, unit = excluded.unit,
                                  ingested_at = excluded.ingested_at
                    """,
                    (
                        station_key,
                        observed_at,
                        reading.metric,
                        reading.value,
                        reading.unit,
                        started_at,
                    ),
                )
            connection.execute(
                """
                UPDATE ingestion_runs
                SET completed_at = ?, status = 'completed', observations_written = ?
                WHERE id = ?
                """,
                (utc_now(), len(records), run_id),
            )
    except Exception as error:
        with connection:
            connection.execute(
                """
                UPDATE ingestion_runs
                SET completed_at = ?, status = 'failed', error = ? WHERE id = ?
                """,
                (utc_now(), str(error), run_id),
            )
        raise
    return IngestionResult(run_id, len(records), len(records))

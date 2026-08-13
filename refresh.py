"""Incremental ECCC refresh orchestration."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from datetime import datetime, timezone

import pandas as pd

from get_yukon_weather import SLEEP_SEC, STATIONS, fetch_year
from myacurite import MyAcuriteClient, load_myacurite_config
from weather_store import (
    IngestionResult,
    ingest_eccc_daily,
    ingest_myacurite_snapshot,
    utc_now,
)

FetchYear = Callable[[int, int], pd.DataFrame]


def refresh_years(now: datetime | None = None) -> tuple[int, ...]:
    """Refresh this year, plus last year while late corrections are plausible."""
    current = now or datetime.now(timezone.utc)
    if current.month == 1:
        return (current.year - 1, current.year)
    return (current.year,)


def refresh_eccc(
    connection: sqlite3.Connection,
    *,
    years: tuple[int, ...] | None = None,
    fetcher: FetchYear = fetch_year,
    sleep_seconds: float = SLEEP_SEC,
) -> tuple[IngestionResult, ...]:
    """Fetch only changing years and idempotently upsert each station."""
    selected_years = years or refresh_years()
    with connection:
        run_id = connection.execute(
            "INSERT INTO refresh_runs (started_at, status) VALUES (?, 'running')",
            (utc_now(),),
        ).lastrowid
    results = []
    try:
        for station_key, station_id in STATIONS.items():
            chunks = []
            for year in selected_years:
                frame = fetcher(station_id, year)
                if not frame.empty:
                    chunks.append(frame)
                if sleep_seconds:
                    time.sleep(sleep_seconds)
            combined = (
                pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
            )
            results.append(
                ingest_eccc_daily(
                    connection,
                    station_key=station_key,
                    station_id=station_id,
                    rows=combined.to_dict(orient="records"),
                )
            )
        with connection:
            connection.execute(
                """
                UPDATE refresh_runs
                SET completed_at = ?, status = 'completed', stations = ?,
                    observations_written = ?
                WHERE id = ?
                """,
                (
                    utc_now(),
                    len(results),
                    sum(result.observations_written for result in results),
                    run_id,
                ),
            )
    except Exception as error:
        with connection:
            connection.execute(
                """
                UPDATE refresh_runs
                SET completed_at = ?, status = 'failed', error = ?
                WHERE id = ?
                """,
                (utc_now(), str(error), run_id),
            )
        raise
    return tuple(results)


def refresh_weather(
    connection: sqlite3.Connection,
    *,
    acurite_client_factory=MyAcuriteClient,
) -> tuple[IngestionResult, ...]:
    """Refresh public ECCC data and the household station when configured."""
    results = list(refresh_eccc(connection))
    config = load_myacurite_config()
    if config is None:
        return tuple(results)
    try:
        snapshots = acurite_client_factory(config).fetch_snapshots()
        for snapshot in snapshots:
            results.append(
                ingest_myacurite_snapshot(
                    connection,
                    station_key=snapshot.station_key,
                    station_name=snapshot.station_name,
                    observed_at=snapshot.observed_at,
                    readings=snapshot.readings,
                )
            )
    except Exception as error:
        with connection:
            connection.execute(
                """
                INSERT INTO refresh_runs
                    (started_at, completed_at, status, error)
                VALUES (?, ?, 'failed', ?)
                """,
                (utc_now(), utc_now(), str(error)),
            )
        raise
    return tuple(results)

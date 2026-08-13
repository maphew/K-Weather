import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd

from myacurite import MyAcuriteSnapshot, SensorReading
from refresh import refresh_eccc, refresh_weather, refresh_years
from weather_store import connect_database


class RefreshTest(unittest.TestCase):
    def setUp(self) -> None:
        self.database = connect_database(":memory:")

    def tearDown(self) -> None:
        self.database.close()

    def test_refreshes_current_year_normally_and_previous_year_in_january(self) -> None:
        self.assertEqual(
            refresh_years(datetime(2026, 8, 13, tzinfo=timezone.utc)), (2026,)
        )
        self.assertEqual(
            refresh_years(datetime(2026, 1, 2, tzinfo=timezone.utc)), (2025, 2026)
        )

    def test_incremental_refresh_is_idempotent_and_records_success(self) -> None:
        calls = []

        def fetcher(station_id, year):
            calls.append((station_id, year))
            if station_id != 50842:
                return pd.DataFrame()
            return pd.DataFrame(
                [
                    {
                        "Station Name": "WHITEHORSE A",
                        "Date/Time": f"{year}-08-11",
                        "Mean Temp (°C)": 12.0,
                    }
                ]
            )

        refresh_eccc(self.database, years=(2026,), fetcher=fetcher, sleep_seconds=0)
        refresh_eccc(self.database, years=(2026,), fetcher=fetcher, sleep_seconds=0)

        self.assertEqual(len(calls), 6)
        self.assertEqual(
            self.database.execute("SELECT count(*) FROM observations").fetchone()[0],
            1,
        )
        self.assertEqual(
            self.database.execute(
                "SELECT status FROM refresh_runs ORDER BY id"
            ).fetchall(),
            [("completed",), ("completed",)],
        )

    def test_fetch_failure_is_recorded_without_exposing_it_to_dashboard(self) -> None:
        def failing_fetcher(_station_id, _year):
            raise RuntimeError("private upstream detail")

        with self.assertRaisesRegex(RuntimeError, "private upstream detail"):
            refresh_eccc(
                self.database,
                years=(2026,),
                fetcher=failing_fetcher,
                sleep_seconds=0,
            )

        status, error = self.database.execute(
            "SELECT status, error FROM refresh_runs"
        ).fetchone()
        self.assertEqual(status, "failed")
        self.assertEqual(error, "private upstream detail")

    @patch("refresh.refresh_eccc", return_value=())
    def test_configured_household_snapshot_runs_on_shared_refresh(self, _refresh_eccc):
        snapshot = MyAcuriteSnapshot(
            station_key="home",
            station_name="AcuRite Iris",
            observed_at="2026-08-13T13:15:00+00:00",
            readings=(SensorReading("temperature", 62.5, "°F"),),
        )

        class Client:
            def __init__(self, _config):
                pass

            def fetch_snapshots(self):
                return (snapshot,)

        environment = {
            "MYACURITE_EMAIL": "person@example.invalid",
            "MYACURITE_PASSWORD": "synthetic-password",
        }
        with patch.dict(os.environ, environment, clear=True):
            refresh_weather(self.database, acurite_client_factory=Client)
            refresh_weather(self.database, acurite_client_factory=Client)

        self.assertEqual(
            self.database.execute("SELECT count(*) FROM observations").fetchone()[0],
            1,
        )
        self.assertEqual(
            self.database.execute(
                "SELECT count(*) FROM ingestion_runs WHERE source = 'myacurite'"
            ).fetchone()[0],
            2,
        )


if __name__ == "__main__":
    unittest.main()

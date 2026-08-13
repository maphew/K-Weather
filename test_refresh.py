import unittest
from datetime import datetime, timezone

import pandas as pd

from refresh import refresh_eccc, refresh_years
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


if __name__ == "__main__":
    unittest.main()

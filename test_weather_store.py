import unittest

import pandas as pd

from get_yukon_weather import merge_preferring_riverdale
from weather_store import connect_database, ingest_eccc_daily


class WeatherStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.database = connect_database(":memory:")

    def tearDown(self) -> None:
        self.database.close()

    def test_duplicate_refresh_updates_without_duplicating(self) -> None:
        rows = [
            {
                "Station Name": "WHITEHORSE A",
                "Climate ID": "2101303",
                "Date/Time": "2026-08-11",
                "Max Temp (°C)": 18.2,
                "Max Temp Flag": "E",
                "Min Temp (°C)": 7.1,
            }
        ]

        first = ingest_eccc_daily(
            self.database, station_key="whitehorse_a", station_id=50842, rows=rows
        )
        rows[0]["Max Temp (°C)"] = 19.0
        second = ingest_eccc_daily(
            self.database, station_key="whitehorse_a", station_id=50842, rows=rows
        )

        count = self.database.execute("SELECT count(*) FROM observations").fetchone()[0]
        value = self.database.execute(
            "SELECT value FROM observations WHERE metric = 'maximum_temperature'"
        ).fetchone()[0]
        run_statuses = self.database.execute(
            "SELECT status FROM ingestion_runs ORDER BY id"
        ).fetchall()
        self.assertEqual(first.observations_written, 2)
        self.assertEqual(second.observations_written, 2)
        self.assertEqual(count, 2)
        self.assertEqual(value, 19.0)
        self.assertEqual(run_statuses, [("completed",), ("completed",)])

    def test_blank_placeholder_day_is_not_stored(self) -> None:
        result = ingest_eccc_daily(
            self.database,
            station_key="riverdale",
            station_id=1618,
            rows=[
                {
                    "Station Name": "WHITEHORSE RIVERDALE",
                    "Climate ID": "2101400",
                    "Date/Time": "2026-01-01",
                    "Max Temp (°C)": None,
                    "Total Precip (mm)": float("nan"),
                }
            ],
        )

        count = self.database.execute("SELECT count(*) FROM observations").fetchone()[0]
        self.assertEqual(result.rows_received, 1)
        self.assertEqual(result.observations_written, 0)
        self.assertEqual(count, 0)

    def test_invalid_row_marks_ingestion_failed(self) -> None:
        with self.assertRaisesRegex(ValueError, "no Date/Time"):
            ingest_eccc_daily(
                self.database,
                station_key="whitehorse_a",
                station_id=50842,
                rows=[{"Max Temp (°C)": 4.0}],
            )

        run = self.database.execute(
            "SELECT status, error FROM ingestion_runs"
        ).fetchone()
        self.assertEqual(run[0], "failed")
        self.assertIn("no Date/Time", run[1])


class StationFallbackTest(unittest.TestCase):
    def test_riverdale_is_preferred_and_airport_fills_missing_day(self) -> None:
        riverdale = pd.DataFrame(
            {"Date/Time": ["2026-01-01"], "Mean Temp (°C)": [-20.0]}
        )
        airport = pd.DataFrame(
            {
                "Date/Time": ["2026-01-01", "2026-01-02"],
                "Mean Temp (°C)": [-18.0, -17.0],
            }
        )

        merged = merge_preferring_riverdale(
            {"riverdale": riverdale, "whitehorse_a": airport}
        )

        self.assertEqual(merged["_source"].tolist(), ["riverdale", "whitehorse_a"])
        self.assertEqual(merged["Mean Temp (°C)"].tolist(), [-20.0, -17.0])


if __name__ == "__main__":
    unittest.main()

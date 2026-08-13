import tempfile
import unittest
from pathlib import Path

from app import create_app
from weather_store import connect_database, ingest_eccc_daily


class DashboardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "weather.sqlite3"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def client(self):
        application = create_app(self.database_path)
        application.config["TESTING"] = True
        return application.test_client()

    def add_rows(self, rows) -> None:
        database = connect_database(self.database_path)
        ingest_eccc_daily(
            database,
            station_key="whitehorse_a",
            station_id=50842,
            rows=rows,
        )
        database.close()

    def test_empty_database_state(self) -> None:
        response = self.client().get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No weather data yet", response.data)
        self.assertNotIn(b"<svg", response.data)

    def test_single_series_state(self) -> None:
        self.add_rows(
            [
                {
                    "Station Name": "WHITEHORSE A",
                    "Date/Time": "2026-08-10",
                    "Mean Temp (°C)": 10.0,
                },
                {
                    "Station Name": "WHITEHORSE A",
                    "Date/Time": "2026-08-11",
                    "Mean Temp (°C)": 12.0,
                },
            ]
        )

        response = self.client().get("/?metric=mean_temperature")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Daily mean", response.data)
        self.assertIn(b"11.0", response.data)
        self.assertEqual(response.data.count(b'data-chart="'), 1)

    def test_multiple_metric_filters(self) -> None:
        self.add_rows(
            [
                {
                    "Station Name": "WHITEHORSE A",
                    "Date/Time": "2026-08-11",
                    "Max Temp (°C)": 18.0,
                    "Min Temp (°C)": 6.0,
                    "Total Precip (mm)": 2.5,
                }
            ]
        )

        response = self.client().get(
            "/?metric=maximum_temperature&metric=precipitation"
            "&start=2026-08-11&end=2026-08-11"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.count(b'data-chart="'), 2)
        self.assertIn(b"Daily high", response.data)
        self.assertIn(b"Total precipitation", response.data)
        self.assertNotIn(
            b'<article class="chart-card" data-chart="minimum_temperature"',
            response.data,
        )

    def test_page_does_not_expose_precise_location_metadata(self) -> None:
        self.add_rows(
            [
                {
                    "Station Name": "WHITEHORSE A",
                    "Climate ID": "SYNTHETIC-STATION",
                    "Longitude (x)": -123.456,
                    "Latitude (y)": 54.321,
                    "Date/Time": "2026-08-11",
                    "Max Temp (°C)": 18.0,
                }
            ]
        )

        response = self.client().get("/")

        self.assertIn(b"Riverdale", response.data)
        self.assertNotIn(b"-123.456", response.data)
        self.assertNotIn(b"54.321", response.data)
        self.assertNotIn(b"SYNTHETIC-STATION", response.data)


if __name__ == "__main__":
    unittest.main()

import csv
import tempfile
import unittest
from pathlib import Path

from dashboard import chart_points
from import_myacurite_csv import import_csv
from myacurite import SensorReading
from weather_store import connect_database, ingest_myacurite_snapshot


class MyAcuriteCsvTest(unittest.TestCase):
    def setUp(self):
        self.database = connect_database(":memory:")
        for key, name in (("home", "AcuRite Iris"), ("sensor_1", "Deck sensor")):
            ingest_myacurite_snapshot(
                self.database,
                station_key=key,
                station_name=name,
                observed_at="2026-08-13T12:00:00+00:00",
                readings=(SensorReading("temperature", 20, "°C"),),
            )
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.csv_path = Path(self.temporary_directory.name) / "private.csv"

    def tearDown(self):
        self.database.close()
        self.temporary_directory.cleanup()

    def write_csv(self):
        columns = [
            "Sensor Name",
            "Sensor Type",
            "Timestamp",
            "Temperature ( C )",
            "Humidity ( RH )",
            "Accumulated Rain ( MM )",
        ]
        rows = [
            [
                "AcuRite Iris",
                "AcuRite Iris®",
                "2026/07/14 10:00 AM",
                "15",
                "40",
                "0.25",
            ],
            [
                "Deck sensor",
                "Temp & Humidity Sensor",
                "2026/07/14 10:05 AM",
                "16",
                "41",
                "",
            ],
        ]
        with self.csv_path.open("w", newline="") as target:
            writer = csv.writer(target)
            writer.writerow(columns)
            writer.writerows(rows)

    def test_imports_all_devices_in_utc_and_is_idempotent(self):
        self.write_csv()

        first = import_csv(self.database, self.csv_path)
        second = import_csv(self.database, self.csv_path)

        history = self.database.execute(
            """
            SELECT station_key, observed_at, metric, value, unit
            FROM observations WHERE interval = 'five_minute'
            ORDER BY station_key, metric
            """
        ).fetchall()
        self.assertEqual(first.rows_received, 2)
        self.assertEqual(first.observations_written, 5)
        self.assertEqual(second.observations_written, 5)
        self.assertEqual(len(history), 5)
        self.assertEqual(history[0][1], "2026-07-14T17:00:00+00:00")
        self.assertIn(
            ("home", "2026-07-14T17:00:00+00:00", "rainfall", 0.25, "mm"), history
        )

    def test_rejects_unknown_auxiliary_station(self):
        self.write_csv()
        with self.csv_path.open() as source:
            rows = list(csv.reader(source))
        rows[2][0] = "Unknown private sensor"
        with self.csv_path.open("w", newline="") as target:
            csv.writer(target).writerows(rows)

        with self.assertRaisesRegex(ValueError, "does not match"):
            import_csv(self.database, self.csv_path)

    def test_chart_downsampling_keeps_endpoints(self):
        points = [(f"2026-01-{index:02d}", float(index)) for index in range(1, 32)]

        sampled = chart_points(points, limit=10)

        self.assertEqual(len(sampled), 10)
        self.assertEqual(sampled[0], points[0])
        self.assertEqual(sampled[-1], points[-1])

    def test_chart_daily_averages_subdaily_points(self):
        points = [
            ("2026-08-01T10:00:00+00:00", 10),
            ("2026-08-01T11:00:00+00:00", 14),
            ("2026-08-02T10:00:00+00:00", 20),
        ]

        sampled = chart_points(points, daily=True)

        self.assertEqual(sampled, [("2026-08-01", 12), ("2026-08-02", 20)])


if __name__ == "__main__":
    unittest.main()

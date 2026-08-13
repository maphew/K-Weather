import tempfile
import unittest
from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from app import create_app
from myacurite import SensorReading
from weather_store import (
    IngestionResult,
    connect_database,
    ingest_eccc_daily,
    ingest_myacurite_snapshot,
)


class DashboardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "weather.sqlite3"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def client(self):
        application = create_app(
            self.database_path,
            username="family",
            password="correct horse battery staple",
            secret_key="test-session-key",
            refresh_token="refresh-secret",
        )
        application.config["TESTING"] = True
        return application.test_client()

    def auth_header(self) -> dict[str, str]:
        credentials = b64encode(b"family:correct horse battery staple").decode()
        return {"Authorization": f"Basic {credentials}"}

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
        response = self.client().get("/", headers=self.auth_header())

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

        response = self.client().get(
            "/?metric=mean_temperature", headers=self.auth_header()
        )

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
            "&start=2026-08-11&end=2026-08-11",
            headers=self.auth_header(),
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

        response = self.client().get("/", headers=self.auth_header())

        self.assertIn(b"Riverdale", response.data)
        self.assertNotIn(b"-123.456", response.data)
        self.assertNotIn(b"54.321", response.data)
        self.assertNotIn(b"SYNTHETIC-STATION", response.data)

    def test_household_snapshots_are_filterable_through_end_of_day(self) -> None:
        database = connect_database(self.database_path)
        ingest_myacurite_snapshot(
            database,
            observed_at="2026-08-13T23:45:00+00:00",
            readings=(SensorReading("temperature", 62.5, "°F"),),
        )
        database.close()

        response = self.client().get(
            "/?metric=temperature&station=myacurite:home"
            "&start=2026-08-13&end=2026-08-13",
            headers=self.auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Riverdale household station \xc2\xb7 AcuRite", response.data)
        self.assertIn(b"62.5 \xc2\xb0F", response.data)
        self.assertIn(b"1 observations", response.data)
        self.assertIn(b"<circle", response.data)

    def test_history_date_range_applies_to_acurite_observations(self) -> None:
        database = connect_database(self.database_path)
        for observed_at, value in (
            ("2026-08-12T12:00:00+00:00", 20),
            ("2026-08-13T12:00:00+00:00", 21),
        ):
            ingest_myacurite_snapshot(
                database,
                station_name="AcuRite Iris",
                observed_at=observed_at,
                readings=(SensorReading("temperature", value, "°C"),),
            )
        database.close()

        response = self.client().get(
            "/?metric=temperature&start=2026-08-13&end=2026-08-13",
            headers=self.auth_header(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"21.0 \xc2\xb0C", response.data)
        self.assertIn(b"1 observations", response.data)
        self.assertNotIn(b"20.0 \xc2\xb0C", response.data)

    def test_current_conditions_show_all_household_sensors_and_wind_direction(
        self,
    ) -> None:
        database = connect_database(self.database_path)
        ingest_myacurite_snapshot(
            database,
            station_key="home",
            station_name="AcuRite Iris",
            observed_at="2026-08-13T16:45:00+00:00",
            readings=(
                SensorReading("temperature", 25.6, "°C"),
                SensorReading("humidity", 44, "%RH"),
                SensorReading("wind_direction", 112.5, ""),
                SensorReading("rainfall", 0.25, "mm"),
            ),
        )
        ingest_myacurite_snapshot(
            database,
            station_key="sensor_1",
            station_name="Greenhouse sensor",
            observed_at="2026-08-13T16:44:00+00:00",
            readings=(
                SensorReading("temperature", 9.5, "°C"),
                SensorReading("humidity", 86, "%RH"),
                SensorReading("dew_point", 7, "°C"),
            ),
        )
        database.close()

        response = self.client().get("/", headers=self.auth_header())

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Current conditions", response.data)
        self.assertIn(b"AcuRite Iris", response.data)
        self.assertIn(b"Greenhouse sensor", response.data)
        self.assertIn(b"25.6 \xc2\xb0C", response.data)
        self.assertIn(b"ESE \xc2\xb7 112.5\xc2\xb0", response.data)
        self.assertIn(b"0.25 mm", response.data)
        self.assertIn(b"44 %", response.data)
        self.assertIn(b"Aug 13, 9:45 AM", response.data)
        self.assertNotIn(b"Data may be stale", response.data)

    def test_stale_condition_explains_threshold_in_tooltip(self) -> None:
        database = connect_database(self.database_path)
        ingest_myacurite_snapshot(
            database,
            station_name="AcuRite Iris",
            observed_at="2020-01-01T00:00:00+00:00",
            readings=(SensorReading("temperature", -20, "°C"),),
        )
        database.close()

        response = self.client().get("/", headers=self.auth_header())

        self.assertIn(b"Data may be stale", response.data)
        self.assertIn(
            b"MyAcuRite has not reported a new reading for more than 12 hours.",
            response.data,
        )

    def test_dashboard_requires_authentication(self) -> None:
        response = self.client().get("/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")

    def test_mobile_friendly_login_session(self) -> None:
        client = self.client()
        rejected = client.post(
            "/login",
            data={"username": "family", "password": "wrong"},
            base_url="https://localhost",
        )
        accepted = client.post(
            "/login",
            data={"username": "family", "password": "correct horse battery staple"},
            base_url="https://localhost",
        )
        dashboard = client.get("/", base_url="https://localhost")

        self.assertIn(b"did not match", rejected.data)
        self.assertEqual(accepted.status_code, 302)
        self.assertEqual(accepted.headers["Location"], "/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b"K-Weather", dashboard.data)

    def test_login_tolerates_mobile_capitalization_and_copy_whitespace(self) -> None:
        client = self.client()

        response = client.post(
            "/login",
            data={
                "username": " Family ",
                "password": " correct horse battery staple\n",
            },
            base_url="https://localhost",
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_refresh_requires_bearer_token(self) -> None:
        response = self.client().post("/refresh")

        self.assertEqual(response.status_code, 401)

    def test_refresh_rejects_concurrent_request(self) -> None:
        entered = Event()
        release = Event()

        def blocking_refresher(_database):
            entered.set()
            release.wait(timeout=5)
            return (IngestionResult(1, 1, 1),)

        application = create_app(
            self.database_path,
            username="family",
            password="password",
            secret_key="test-session-key",
            refresh_token=None,
            refresh_token_verifier=lambda token: token == "valid-oidc-token",
            refresher=blocking_refresher,
        )
        application.config["TESTING"] = True
        headers = {"Authorization": "Bearer valid-oidc-token"}
        with ThreadPoolExecutor(max_workers=1) as executor:
            first = executor.submit(
                lambda: application.test_client().post("/refresh", headers=headers)
            )
            self.assertTrue(entered.wait(timeout=2))
            second = application.test_client().post("/refresh", headers=headers)
            release.set()
            first_response = first.result(timeout=2)

        self.assertEqual(second.status_code, 409)
        self.assertEqual(first_response.status_code, 200)


if __name__ == "__main__":
    unittest.main()

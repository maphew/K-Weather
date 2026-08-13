import os
import unittest
from unittest.mock import patch

import requests

from myacurite import (
    MyAcuriteClient,
    MyAcuriteConfig,
    MyAcuriteError,
    SensorReading,
    parse_snapshots,
)
from weather_store import connect_database, ingest_myacurite_snapshot


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("synthetic upstream failure")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, posts, gets):
        self.posts = list(posts)
        self.gets = list(gets)
        self.post_calls = []
        self.get_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self.posts.pop(0)

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self.gets.pop(0)


def synthetic_dashboard():
    return {
        "timezone": "America/Whitehorse",
        "latitude": 54.321,
        "longitude": -123.456,
        "devices": [
            {
                "name": "AcuRite Iris",
                "model_code": "5in1WS",
                "last_check_in_at": "2026-08-13T06:15:00-07:00",
                "sensors": [
                    {
                        "sensor_name": "Temperature",
                        "last_reading_value": "62.5",
                        "chart_unit": "F",
                    },
                    {
                        "sensor_name": "Humidity",
                        "last_reading_value": 41,
                        "chart_unit": "%",
                    },
                    {
                        "sensor_name": "Lightning Closest Strike Distance",
                        "last_reading_value": None,
                        "chart_unit": "mi",
                    },
                ],
                "wired_sensors": [],
            },
            {
                "name": "Greenhouse sensor",
                "model_code": "2in1T",
                "last_check_in_at": "2026-08-13T06:14:00-07:00",
                "sensors": [
                    {
                        "sensor_name": "Temperature",
                        "last_reading_value": 49.1,
                        "chart_unit": "F",
                    },
                    {
                        "sensor_name": "Humidity",
                        "last_reading_value": 86,
                        "chart_unit": "%RH",
                    },
                ],
            },
        ],
    }


class MyAcuriteParsingTest(unittest.TestCase):
    def test_parses_timestamp_units_and_null_readings(self):
        snapshots = parse_snapshots(synthetic_dashboard())
        snapshot = snapshots[0]

        self.assertEqual(len(snapshots), 2)
        self.assertEqual(snapshot.station_key, "home")
        self.assertEqual(snapshot.station_name, "AcuRite Iris")
        self.assertEqual(snapshot.observed_at, "2026-08-13T13:15:00+00:00")
        self.assertEqual(
            snapshot.readings,
            (
                SensorReading("temperature", 62.5, "°F"),
                SensorReading("humidity", 41.0, "%"),
            ),
        )
        self.assertEqual(snapshots[1].station_key, "sensor_1")
        self.assertEqual(snapshots[1].station_name, "Greenhouse sensor")
        self.assertEqual(snapshots[1].observed_at, "2026-08-13T13:14:00+00:00")

    def test_rejects_schema_change_without_including_payload(self):
        private_value = "private-device-value"
        with self.assertRaises(MyAcuriteError) as raised:
            parse_snapshots({"unexpected": private_value})

        self.assertNotIn(private_value, str(raised.exception))


class MyAcuriteClientTest(unittest.TestCase):
    def setUp(self):
        self.config = MyAcuriteConfig("person@example.invalid", "private-password")
        self.login = FakeResponse(
            {
                "token_id": "synthetic-token",
                "user": {"account_users": [{"account_id": "synthetic-account"}]},
            }
        )

    def test_logs_in_and_fetches_dashboard_with_token(self):
        session = FakeSession(
            [self.login],
            [
                FakeResponse({"account_hubs": [{"id": 12345}]}),
                FakeResponse(synthetic_dashboard()),
            ],
        )

        snapshots = MyAcuriteClient(self.config, session=session).fetch_snapshots()

        self.assertEqual(snapshots[0].readings[0].metric, "temperature")
        self.assertEqual(session.post_calls[0][1]["timeout"], 15)
        self.assertEqual(
            session.get_calls[0][1]["headers"], {"x-one-vue-token": "synthetic-token"}
        )
        self.assertTrue(session.get_calls[1][0].endswith("/dashboard/hubs/12345"))

    def test_reauthenticates_once_after_unauthorized_response(self):
        session = FakeSession(
            [self.login, self.login],
            [
                FakeResponse(status_code=401),
                FakeResponse({"account_hubs": [{"id": 12345}]}),
                FakeResponse(synthetic_dashboard()),
            ],
        )

        MyAcuriteClient(self.config, session=session).fetch_snapshots()

        self.assertEqual(len(session.post_calls), 2)
        self.assertEqual(len(session.get_calls), 3)

    def test_login_failure_is_sanitized(self):
        session = FakeSession([FakeResponse(status_code=401)], [])

        with self.assertRaisesRegex(MyAcuriteError, "sign-in failed") as raised:
            MyAcuriteClient(self.config, session=session).fetch_snapshots()

        message = str(raised.exception)
        self.assertNotIn(self.config.email, message)
        self.assertNotIn(self.config.password, message)

    def test_requires_exactly_one_discovered_hub(self):
        session = FakeSession(
            [self.login], [FakeResponse({"account_hubs": [{"id": 1}, {"id": 2}]})]
        )

        with self.assertRaisesRegex(MyAcuriteError, "exactly one hub"):
            MyAcuriteClient(self.config, session=session).fetch_snapshots()


class MyAcuriteStoreTest(unittest.TestCase):
    def test_duplicate_snapshot_updates_without_account_metadata(self):
        database = connect_database(":memory:")
        readings = [SensorReading("temperature", 62.5, "°F")]

        ingest_myacurite_snapshot(
            database,
            observed_at="2026-08-13T13:15:00+00:00",
            readings=readings,
        )
        readings[0] = SensorReading("temperature", 63.0, "°F")
        ingest_myacurite_snapshot(
            database,
            observed_at="2026-08-13T13:15:00+00:00",
            readings=readings,
        )

        self.assertEqual(
            database.execute("SELECT count(*) FROM observations").fetchone()[0], 1
        )
        self.assertEqual(
            database.execute("SELECT value FROM observations").fetchone()[0], 63.0
        )
        station = database.execute(
            "SELECT station_key, external_id, name FROM stations"
        ).fetchone()
        self.assertEqual(station, ("home", None, "Riverdale household station"))
        database.close()

    def test_no_configuration_is_distinct_from_partial_configuration(self):
        from myacurite import load_myacurite_config

        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(load_myacurite_config())
        with (
            patch.dict(os.environ, {"MYACURITE_EMAIL": "user"}, clear=True),
            self.assertRaisesRegex(MyAcuriteError, "incomplete"),
        ):
            load_myacurite_config()


if __name__ == "__main__":
    unittest.main()

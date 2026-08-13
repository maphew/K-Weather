import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backup import (
    BackupConfig,
    BackupError,
    create_sqlite_snapshot,
    database_fingerprint,
)
from weather_store import connect_database


class BackupTest(unittest.TestCase):
    def test_snapshot_is_consistent_and_independent_of_live_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "live.sqlite3"
            snapshot = Path(directory) / "snapshot.sqlite3"
            connection = connect_database(source)
            with connection:
                connection.execute(
                    "INSERT INTO refresh_runs (started_at, status) VALUES ('now', 'running')"
                )

            create_sqlite_snapshot(source, snapshot)
            with connection:
                connection.execute("DELETE FROM refresh_runs")
            connection.close()

            copied = sqlite3.connect(snapshot)
            self.assertEqual(
                copied.execute("SELECT count(*) FROM refresh_runs").fetchone()[0], 1
            )
            copied.close()
            self.assertEqual(snapshot.stat().st_mode & 0o777, 0o600)

    def test_fingerprint_rejects_a_non_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "invalid.sqlite3"
            invalid.write_text("not sqlite", encoding="utf-8")
            with self.assertRaisesRegex(BackupError, "verified"):
                database_fingerprint(invalid)

    def test_configuration_does_not_accept_missing_secrets(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            self.assertRaisesRegex(BackupError, "incomplete"),
        ):
            BackupConfig.from_environment()


if __name__ == "__main__":
    unittest.main()

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backup import (
    BackupConfig,
    BackupError,
    backup_database,
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

    def test_backup_clears_stale_locks_and_groups_retention_without_temp_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "live.sqlite3"
            password = root / "restic-password"
            rclone = root / "rclone.conf"
            connect_database(database).close()
            password.touch(mode=0o600)
            rclone.touch(mode=0o600)
            config = BackupConfig(database, "repository", password, rclone)
            calls: list[tuple[str, ...]] = []

            def fake_restic(
                _config: BackupConfig, *arguments: str, cwd: Path | None = None
            ) -> None:
                calls.append(arguments)
                if arguments[0] == "restore":
                    target = Path(arguments[arguments.index("--target") + 1])
                    target.mkdir(parents=True)
                    create_sqlite_snapshot(database, target / "k-weather.sqlite3")

            with patch("backup.run_restic", side_effect=fake_restic):
                backup_database(config)

            self.assertEqual(calls[0], ("unlock",))
            forget = next(call for call in calls if call[0] == "forget")
            group_by = forget.index("--group-by")
            self.assertEqual(forget[group_by + 1], "host,tags")


if __name__ == "__main__":
    unittest.main()

"""Encrypted, versioned off-site backups for the K-Weather database."""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


class BackupError(RuntimeError):
    """A privacy-safe backup failure."""


@dataclass(frozen=True)
class BackupConfig:
    database: Path
    repository: str
    password_file: Path
    rclone_config: Path

    @classmethod
    def from_environment(cls) -> BackupConfig:
        values = {
            "K_WEATHER_DB": os.environ.get(
                "K_WEATHER_DB", "yukon_weather/k-weather.sqlite3"
            ),
            "K_WEATHER_BACKUP_REPOSITORY": os.environ.get(
                "K_WEATHER_BACKUP_REPOSITORY"
            ),
            "K_WEATHER_RESTIC_PASSWORD_FILE": os.environ.get(
                "K_WEATHER_RESTIC_PASSWORD_FILE"
            ),
            "RCLONE_CONFIG": os.environ.get("RCLONE_CONFIG"),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise BackupError("backup configuration is incomplete")
        return cls(
            database=Path(values["K_WEATHER_DB"]),
            repository=values["K_WEATHER_BACKUP_REPOSITORY"],
            password_file=Path(values["K_WEATHER_RESTIC_PASSWORD_FILE"]),
            rclone_config=Path(values["RCLONE_CONFIG"]),
        )

    def environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update(
            RESTIC_REPOSITORY=self.repository,
            RESTIC_PASSWORD_FILE=str(self.password_file),
            RCLONE_CONFIG=str(self.rclone_config),
        )
        return environment


def create_sqlite_snapshot(source: Path, destination: Path) -> None:
    """Use SQLite's online backup API rather than copying live DB/WAL files."""
    if not source.is_file():
        raise BackupError("weather database is unavailable")
    source_connection = sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    except sqlite3.Error as error:
        raise BackupError("could not create a consistent database snapshot") from error
    finally:
        destination_connection.close()
        source_connection.close()
    destination.chmod(0o600)


def database_fingerprint(path: Path) -> tuple[int, str | None]:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise BackupError("restored database failed its integrity check")
        return connection.execute(
            "SELECT count(*), max(observed_at) FROM observations"
        ).fetchone()
    except sqlite3.Error as error:
        raise BackupError("restored database could not be verified") from error
    finally:
        connection.close()


def run_restic(config: BackupConfig, *arguments: str, cwd: Path | None = None) -> None:
    try:
        subprocess.run(
            ("restic", *arguments),
            cwd=cwd,
            env=config.environment(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise BackupError("encrypted backup operation failed") from error


def initialize_repository(config: BackupConfig) -> None:
    run_restic(config, "init")


def backup_database(config: BackupConfig) -> None:
    """Snapshot, back up, retain, check, restore, and verify the private DB."""
    for private_file in (config.password_file, config.rclone_config):
        if not private_file.is_file() or private_file.stat().st_mode & 0o077:
            raise BackupError("backup secret files are missing or not private")

    with tempfile.TemporaryDirectory(prefix="k-weather-backup-") as directory:
        workspace = Path(directory)
        snapshot = workspace / "k-weather.sqlite3"
        create_sqlite_snapshot(config.database, snapshot)
        expected = database_fingerprint(snapshot)

        run_restic(
            config,
            "backup",
            snapshot.name,
            "--host",
            "k-weather-sprite",
            "--tag",
            "k-weather",
            cwd=workspace,
        )
        run_restic(
            config,
            "forget",
            "--host",
            "k-weather-sprite",
            "--tag",
            "k-weather",
            "--keep-last",
            "14",
            "--keep-daily",
            "30",
            "--keep-weekly",
            "52",
            "--keep-monthly",
            "1200",
            "--prune",
        )
        run_restic(config, "check")

        restore_directory = workspace / "restore"
        run_restic(
            config,
            "restore",
            "latest",
            "--host",
            "k-weather-sprite",
            "--tag",
            "k-weather",
            "--target",
            str(restore_directory),
        )
        restored = restore_directory / snapshot.name
        if not restored.is_file() or database_fingerprint(restored) != expected:
            raise BackupError("restored database does not match its snapshot")

        shutil.rmtree(restore_directory, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("init", "backup"))
    arguments = parser.parse_args()
    try:
        config = BackupConfig.from_environment()
        if arguments.operation == "init":
            initialize_repository(config)
        else:
            backup_database(config)
    except BackupError as error:
        parser.exit(1, f"backup failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

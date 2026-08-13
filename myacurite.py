"""Minimal client for current MyAcuRite dashboard readings.

MyAcuRite does not publish or support this API. Keep account-scoped values in
memory only and expose only generic errors to callers and logs.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

API_ROOT = "https://marapi.myacurite.com"
TIMEOUT_SECONDS = 15


class MyAcuriteError(RuntimeError):
    """A sanitized MyAcuRite failure safe to record or log."""


@dataclass(frozen=True)
class MyAcuriteConfig:
    email: str
    password: str


@dataclass(frozen=True)
class SensorReading:
    metric: str
    value: float
    unit: str


@dataclass(frozen=True)
class MyAcuriteSnapshot:
    station_key: str
    station_name: str
    observed_at: str
    readings: tuple[SensorReading, ...]


@dataclass(frozen=True)
class MyAcuriteHistoryRow:
    station_key: str
    station_name: str
    observed_at: str
    readings: tuple[SensorReading, ...]


RAW_UNITS = {
    "C": ("C", "°C"),
    "F": ("F", "°F"),
    "%": ("RH", "%"),
    "%RH": ("RH", "%RH"),
    "km/h": ("KPH", "km/h"),
    "mph": ("MPH", "mph"),
    "hPa": ("HPA", "hPa"),
    "inHg": ("INHG", "inHg"),
    "mm": ("MM", "mm"),
    "in": ("IN", "in"),
    "mi": ("MI", "mi"),
    "": ("", ""),
}


def load_myacurite_config() -> MyAcuriteConfig | None:
    values = {
        "email": os.environ.get("MYACURITE_EMAIL"),
        "password": os.environ.get("MYACURITE_PASSWORD"),
    }
    if not any(values.values()):
        return None
    if not all(values.values()):
        raise MyAcuriteError("MyAcuRite configuration is incomplete")
    return MyAcuriteConfig(**values)


def metric_key(sensor_name: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", sensor_name.strip().lower()).strip("_")
    if not key:
        raise MyAcuriteError("MyAcuRite returned an invalid sensor")
    return key


def station_name(value: Any, fallback: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return fallback
    name = " ".join(value.split())
    words = name.split()
    midpoint = len(words) // 2
    if len(words) % 2 == 0 and [word.casefold() for word in words[:midpoint]] == [
        word.casefold() for word in words[midpoint:]
    ]:
        return " ".join(words[:midpoint])
    return name


def display_unit(unit: Any) -> str:
    text = "" if unit is None else str(unit).strip()
    return f"°{text}" if text in {"C", "F"} else text


def normalize_timestamp(value: Any, timezone_name: Any = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MyAcuriteError("MyAcuRite returned no observation timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            if not isinstance(timezone_name, str) or not timezone_name:
                raise ValueError
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    except (ValueError, ZoneInfoNotFoundError):
        raise MyAcuriteError(
            "MyAcuRite returned an invalid observation timestamp"
        ) from None
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_readings(device: Any) -> tuple[SensorReading, ...]:
    try:
        sensors = tuple(device.get("sensors") or ()) + tuple(
            device.get("wired_sensors") or ()
        )
    except (AttributeError, TypeError):
        raise MyAcuriteError(
            "MyAcuRite returned an unexpected dashboard response"
        ) from None

    readings = {}
    for sensor in sensors:
        try:
            value = sensor.get("last_reading_value")
            if value is None or value == "":
                continue
            metric = metric_key(sensor["sensor_name"])
            readings[metric] = SensorReading(
                metric=metric,
                value=float(value),
                unit=display_unit(sensor.get("chart_unit")),
            )
        except (KeyError, TypeError, ValueError):
            raise MyAcuriteError(
                "MyAcuRite returned an invalid sensor reading"
            ) from None
    if not readings:
        raise MyAcuriteError("MyAcuRite returned no usable sensor readings")
    return tuple(readings.values())


def parse_snapshots(payload: Any) -> tuple[MyAcuriteSnapshot, ...]:
    try:
        devices = payload["devices"]
        timezone_name = payload.get("timezone")
        if not isinstance(devices, list) or not devices:
            raise TypeError
        iris_count = sum(device.get("model_code") == "5in1WS" for device in devices)
        if iris_count != 1:
            raise TypeError
    except (AttributeError, KeyError, TypeError):
        raise MyAcuriteError(
            "MyAcuRite returned an unexpected dashboard response"
        ) from None

    snapshots = []
    auxiliary_index = 0
    for device in devices:
        is_iris = device.get("model_code") == "5in1WS"
        if is_iris:
            station_key = "home"
            fallback_name = "AcuRite Iris"
        else:
            auxiliary_index += 1
            station_key = f"sensor_{auxiliary_index}"
            fallback_name = f"Household sensor {auxiliary_index}"
        display_name = station_name(device.get("name"), fallback_name)
        try:
            observed_at = normalize_timestamp(
                device["last_check_in_at"], device.get("timezone") or timezone_name
            )
        except (AttributeError, KeyError, TypeError):
            raise MyAcuriteError(
                "MyAcuRite returned an unexpected dashboard response"
            ) from None
        snapshots.append(
            MyAcuriteSnapshot(
                station_key=station_key,
                station_name=display_name,
                observed_at=observed_at,
                readings=parse_readings(device),
            )
        )
    return tuple(snapshots)


def parse_history_rows(
    device: Any,
    payload: Any,
    *,
    station_key: str,
    station_display_name: str,
) -> tuple[MyAcuriteHistoryRow, ...]:
    """Normalize one private five-minute summary without retaining identifiers."""
    try:
        sensors = tuple(device.get("sensors") or ()) + tuple(
            device.get("wired_sensors") or ()
        )
        channels = {}
        for sensor in sensors:
            channel = str(sensor["channel"])
            chart_unit = (
                "" if sensor.get("chart_unit") is None else str(sensor["chart_unit"])
            )
            raw_unit, unit = RAW_UNITS[chart_unit]
            channels[channel] = (metric_key(sensor["sensor_name"]), raw_unit, unit)
        if not isinstance(payload, dict):
            raise TypeError
    except (AttributeError, KeyError, TypeError):
        raise MyAcuriteError(
            "MyAcuRite returned an unexpected history response"
        ) from None

    rows: dict[str, dict[str, SensorReading]] = {}
    try:
        for channel, (metric, raw_unit, unit) in channels.items():
            for item in payload.get(channel, ()):
                observed_at = normalize_timestamp(item["happened_at"])
                value = item["raw_values"].get(raw_unit)
                if value is None or value == "":
                    continue
                rows.setdefault(observed_at, {})[metric] = SensorReading(
                    metric, float(value), unit
                )
    except (AttributeError, KeyError, TypeError, ValueError):
        raise MyAcuriteError("MyAcuRite returned invalid history data") from None
    return tuple(
        MyAcuriteHistoryRow(
            station_key=station_key,
            station_name=station_display_name,
            observed_at=observed_at,
            readings=tuple(readings.values()),
        )
        for observed_at, readings in sorted(rows.items())
        if readings
    )


def five_minute_urls(summary_url: Any, days: int = 3) -> tuple[str, ...]:
    """Derive recent files while leaving the account-linked path in memory only."""
    if not isinstance(summary_url, str):
        raise MyAcuriteError("MyAcuRite returned no history location")
    parsed = urlparse(summary_url)
    parts = parsed.path.rsplit("/", 2)
    try:
        if (
            parsed.scheme != "https"
            or parsed.hostname != "dataapi.myacurite.com"
            or len(parts) != 3
            or parts[1] != "1h-summaries"
            or not parts[2].endswith(".json")
        ):
            raise ValueError
        latest = date.fromisoformat(parts[2].removesuffix(".json"))
    except (TypeError, ValueError):
        raise MyAcuriteError("MyAcuRite returned an invalid history location") from None
    return tuple(
        urlunparse(
            parsed._replace(
                path=(
                    f"{parts[0]}/5m-summaries/"
                    f"{(latest - timedelta(days=offset)).isoformat()}.json"
                ),
                query="",
                fragment="",
            )
        )
        for offset in range(days)
    )


class MyAcuriteClient:
    def __init__(
        self,
        config: MyAcuriteConfig,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self.config = config
        self.session = session or requests.Session()
        self._token: str | None = None
        self._account_id: str | None = None
        self._hub_id: str | None = None
        self._dashboard: Any = None

    def _login(self) -> None:
        try:
            response = self.session.post(
                f"{API_ROOT}/users/login",
                json={
                    "remember": True,
                    "email": self.config.email,
                    "password": self.config.password,
                },
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            token = payload["token_id"]
            account_id = payload["user"]["account_users"][0]["account_id"]
            if not isinstance(token, str) or not token or account_id is None:
                raise TypeError
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
            raise MyAcuriteError("MyAcuRite sign-in failed") from None
        self._token = token
        self._account_id = str(account_id)

    def _authenticated_get(self, path: str, *, retried: bool = False):
        if not self._token or not self._account_id:
            self._login()
        try:
            response = self.session.get(
                f"{API_ROOT}/accounts/{self._account_id}/{path}",
                headers={"x-one-vue-token": self._token},
                timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException:
            raise MyAcuriteError("MyAcuRite dashboard request failed") from None
        if response.status_code == 401 and not retried:
            self._token = None
            self._account_id = None
            return self._authenticated_get(path, retried=True)
        return response

    def _discover_hub_id(self) -> None:
        response = self._authenticated_get("dashboard/hubs")
        try:
            response.raise_for_status()
            hubs = response.json()["account_hubs"]
            if len(hubs) != 1 or hubs[0].get("id") is None:
                raise MyAcuriteError("MyAcuRite account must contain exactly one hub")
            self._hub_id = str(hubs[0]["id"])
        except MyAcuriteError:
            raise
        except (requests.RequestException, ValueError, KeyError, TypeError):
            raise MyAcuriteError("MyAcuRite hub discovery failed") from None

    def _fetch_dashboard(self) -> Any:
        if self._dashboard is not None:
            return self._dashboard
        if not self._hub_id:
            self._discover_hub_id()
        response = self._authenticated_get(f"dashboard/hubs/{self._hub_id}")
        try:
            response.raise_for_status()
            self._dashboard = response.json()
            return self._dashboard
        except (requests.RequestException, ValueError):
            raise MyAcuriteError("MyAcuRite dashboard request failed") from None

    def fetch_snapshots(self) -> tuple[MyAcuriteSnapshot, ...]:
        return parse_snapshots(self._fetch_dashboard())

    def fetch_history(self) -> tuple[MyAcuriteHistoryRow, ...]:
        payload = self._fetch_dashboard()
        snapshots = parse_snapshots(payload)
        rows = []
        try:
            devices = payload["devices"]
            for device, snapshot in zip(devices, snapshots, strict=True):
                summary_files = device["summary_files"]
                if not isinstance(summary_files, list) or not summary_files:
                    raise TypeError
                for url in five_minute_urls(summary_files[0]):
                    response = self.session.get(url, timeout=TIMEOUT_SECONDS)
                    if response.status_code == 404:
                        continue
                    response.raise_for_status()
                    rows.extend(
                        parse_history_rows(
                            device,
                            response.json(),
                            station_key=snapshot.station_key,
                            station_display_name=snapshot.station_name,
                        )
                    )
        except MyAcuriteError:
            raise
        except (
            requests.RequestException,
            ValueError,
            AttributeError,
            KeyError,
            TypeError,
        ):
            raise MyAcuriteError("MyAcuRite history request failed") from None
        return tuple(rows)

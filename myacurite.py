"""Minimal client for current MyAcuRite dashboard readings.

MyAcuRite does not publish or support this API. Keep account-scoped values in
memory only and expose only generic errors to callers and logs.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
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
    observed_at: str
    readings: tuple[SensorReading, ...]


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


def parse_snapshot(payload: Any) -> MyAcuriteSnapshot:
    try:
        devices = payload["devices"]
        device = next(
            (item for item in devices if item.get("model_code") == "5in1WS"),
            devices[0] if len(devices) == 1 else None,
        )
        if device is None:
            raise KeyError
        observed_at = normalize_timestamp(
            device["last_check_in_at"], payload.get("timezone")
        )
        sensors = tuple(device.get("sensors") or ()) + tuple(
            device.get("wired_sensors") or ()
        )
    except (KeyError, IndexError, TypeError):
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
    return MyAcuriteSnapshot(observed_at=observed_at, readings=tuple(readings.values()))


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

    def fetch_snapshot(self) -> MyAcuriteSnapshot:
        if not self._hub_id:
            self._discover_hub_id()
        response = self._authenticated_get(f"dashboard/hubs/{self._hub_id}")
        try:
            response.raise_for_status()
            return parse_snapshot(response.json())
        except (requests.RequestException, ValueError):
            raise MyAcuriteError("MyAcuRite dashboard request failed") from None

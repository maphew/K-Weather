"""Read-only dashboard queries and chart preparation."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

METRIC_LABELS = {
    "maximum_temperature": "Daily high",
    "minimum_temperature": "Daily low",
    "mean_temperature": "Daily mean",
    "heating_degree_days": "Heating degree days",
    "cooling_degree_days": "Cooling degree days",
    "rain": "Rain",
    "snow": "Snowfall",
    "precipitation": "Total precipitation",
    "snow_on_ground": "Snow on ground",
    "maximum_gust_direction": "Strongest gust direction",
    "maximum_gust_speed": "Strongest gust speed",
    "temperature": "Temperature",
    "humidity": "Humidity",
    "pressure": "Pressure",
    "wind_speed": "Wind speed",
    "wind_direction": "Wind direction",
    "wind_speed_average": "Average wind speed",
    "uv_index": "UV index",
    "rainfall": "Rainfall",
    "wind_chill": "Wind chill",
    "dew_point": "Dew point",
    "light_intensity": "Light intensity",
}

DEFAULT_METRICS = (
    "maximum_temperature",
    "minimum_temperature",
    "mean_temperature",
)

COLORS = ("#d95d39", "#277da1", "#4d908e", "#9c6644", "#7b2cbf")


@dataclass(frozen=True)
class StationOption:
    key: str
    label: str


@dataclass(frozen=True)
class MetricOption:
    key: str
    label: str
    unit: str


@dataclass(frozen=True)
class ChartSeries:
    label: str
    color: str
    points: str
    count: int


@dataclass(frozen=True)
class MetricChart:
    key: str
    label: str
    unit: str
    minimum: float
    maximum: float
    average: float
    latest: float
    latest_date: str
    series: tuple[ChartSeries, ...]


@dataclass(frozen=True)
class DashboardOptions:
    first_date: str | None
    last_date: str | None
    stations: tuple[StationOption, ...]
    metrics: tuple[MetricOption, ...]


@dataclass(frozen=True)
class RefreshStatus:
    completed_at: str | None
    failed_at: str | None


def load_refresh_status(connection: sqlite3.Connection) -> RefreshStatus:
    completed = connection.execute(
        "SELECT max(completed_at) FROM refresh_runs WHERE status = 'completed'"
    ).fetchone()[0]
    failed = connection.execute(
        "SELECT max(completed_at) FROM refresh_runs WHERE status = 'failed'"
    ).fetchone()[0]
    return RefreshStatus(completed_at=completed, failed_at=failed)


def load_options(connection: sqlite3.Connection) -> DashboardOptions:
    bounds = connection.execute(
        "SELECT min(substr(observed_at, 1, 10)), max(substr(observed_at, 1, 10)) "
        "FROM observations"
    ).fetchone()
    station_rows = connection.execute(
        """
        SELECT s.source, s.station_key, s.name
        FROM stations AS s
        WHERE EXISTS (
            SELECT 1 FROM observations AS o
            WHERE o.source = s.source AND o.station_key = s.station_key
        )
        ORDER BY s.name, s.source
        """
    ).fetchall()
    metric_rows = connection.execute(
        """
        SELECT metric, min(unit)
        FROM observations
        GROUP BY metric
        ORDER BY metric
        """
    ).fetchall()
    return DashboardOptions(
        first_date=bounds[0],
        last_date=bounds[1],
        stations=tuple(
            StationOption(
                key=f"{source}:{station_key}",
                label=f"{name} · {source_label(source)}",
            )
            for source, station_key, name in station_rows
        ),
        metrics=tuple(
            MetricOption(metric, METRIC_LABELS.get(metric, metric), unit)
            for metric, unit in metric_rows
        ),
    )


def source_label(source: str) -> str:
    return "AcuRite" if source == "myacurite" else source.upper()


def timestamp(value: str) -> float:
    if len(value) == 10:
        parsed = datetime.combine(date.fromisoformat(value), time(), timezone.utc)
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def default_start(options: DashboardOptions) -> str | None:
    if not options.first_date or not options.last_date:
        return None
    first = date.fromisoformat(options.first_date)
    last = date.fromisoformat(options.last_date)
    return max(first, last - timedelta(days=365)).isoformat()


def load_charts(
    connection: sqlite3.Connection,
    *,
    start: str,
    end: str,
    station_keys: tuple[str, ...],
    metrics: tuple[str, ...],
) -> tuple[MetricChart, ...]:
    if not station_keys or not metrics:
        return ()
    stations = [tuple(value.split(":", 1)) for value in station_keys]
    station_clause = " OR ".join(
        "(o.source = ? AND o.station_key = ?)" for _ in stations
    )
    metric_clause = ", ".join("?" for _ in metrics)
    end_exclusive = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    parameters: list[str] = [start, end_exclusive]
    for source, station_key in stations:
        parameters.extend((source, station_key))
    parameters.extend(metrics)
    rows = connection.execute(
        f"""
        SELECT o.metric, o.unit, o.observed_at, o.value, s.name, s.source
        FROM observations AS o
        JOIN stations AS s
          ON s.source = o.source AND s.station_key = o.station_key
        WHERE o.observed_at >= ? AND o.observed_at < ?
          AND ({station_clause})
          AND o.metric IN ({metric_clause})
        ORDER BY o.metric, s.name, s.source, o.observed_at
        """,
        parameters,
    ).fetchall()

    grouped: dict[str, dict[str, list[tuple[str, float]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    units: dict[str, str] = {}
    for metric, unit, observed_at, value, station_name, source in rows:
        units[metric] = unit
        station_label = f"{station_name} · {source_label(source)}"
        grouped[metric][station_label].append((observed_at, value))

    charts = []
    for metric in metrics:
        station_values = grouped.get(metric)
        if not station_values:
            continue
        values = [value for points in station_values.values() for _, value in points]
        minimum = min(values)
        maximum = max(values)
        y_span = maximum - minimum or 1.0
        start_timestamp = timestamp(start)
        end_timestamp = timestamp(end_exclusive)
        x_span = end_timestamp - start_timestamp or 1
        series = []
        latest_date, latest = max(
            (point for points in station_values.values() for point in points),
            key=lambda point: point[0],
        )
        for index, (station_label, points) in enumerate(station_values.items()):
            coordinates = []
            for observed_at, value in points:
                x = 52 + 926 * ((timestamp(observed_at) - start_timestamp) / x_span)
                y = 18 + 204 * ((maximum - value) / y_span)
                coordinates.append(f"{x:.1f},{y:.1f}")
            series.append(
                ChartSeries(
                    label=station_label,
                    color=COLORS[index % len(COLORS)],
                    points=" ".join(coordinates),
                    count=len(points),
                )
            )
        charts.append(
            MetricChart(
                key=metric,
                label=METRIC_LABELS.get(metric, metric),
                unit=units[metric],
                minimum=minimum,
                maximum=maximum,
                average=sum(values) / len(values),
                latest=latest,
                latest_date=latest_date,
                series=tuple(series),
            )
        )
    return tuple(charts)

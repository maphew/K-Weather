"""Read-only dashboard queries and chart preparation."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

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
    "feels_like": "Feels like",
}

DEFAULT_METRICS = (
    "maximum_temperature",
    "minimum_temperature",
    "mean_temperature",
    "temperature",
)

COLORS = (
    "#d95d39",
    "#277da1",
    "#4d908e",
    "#9c6644",
    "#7b2cbf",
    "#f8961e",
    "#577590",
    "#43aa8b",
)

TEMPERATURE_METRICS = {
    "maximum_temperature",
    "minimum_temperature",
    "mean_temperature",
    "temperature",
}


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
    coordinates: tuple[tuple[float, float], ...]
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


@dataclass(frozen=True)
class CurrentReading:
    metric: str
    label: str
    display_value: str


@dataclass(frozen=True)
class CurrentStation:
    key: str
    name: str
    updated_at: str
    stale: bool
    readings: tuple[CurrentReading, ...]


CURRENT_METRIC_ORDER = {
    metric: index
    for index, metric in enumerate(
        (
            "temperature",
            "feels_like",
            "humidity",
            "dew_point",
            "pressure",
            "wind_speed",
            "wind_speed_average",
            "wind_direction",
            "rainfall",
        )
    )
}


def display_number(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def compass_direction(value: float) -> str:
    directions = (
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    )
    return directions[round((value % 360) / 22.5) % 16]


def current_value(metric: str, value: float, unit: str) -> str:
    if metric == "wind_direction":
        return f"{compass_direction(value)} · {display_number(value)}°"
    display_unit = "%" if unit == "%RH" else unit
    display_value = (
        f"{value:.2f}".rstrip("0").rstrip(".")
        if metric == "rainfall"
        else display_number(value)
    )
    return f"{display_value} {display_unit}".strip()


def local_observation_time(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(ZoneInfo("America/Whitehorse")).strftime(
        "%b %-d, %-I:%M %p"
    )


def observation_is_stale(value: str) -> bool:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - parsed.astimezone(timezone.utc) > timedelta(
        hours=12
    )


def load_current_conditions(
    connection: sqlite3.Connection,
) -> tuple[CurrentStation, ...]:
    rows = connection.execute(
        """
        SELECT s.station_key, s.name, o.observed_at, o.metric, o.value, o.unit
        FROM stations AS s
        JOIN observations AS o
          ON o.source = s.source AND o.station_key = s.station_key
        WHERE s.source = 'myacurite'
          AND o.observed_at = (
              SELECT max(latest.observed_at)
              FROM observations AS latest
              WHERE latest.source = o.source
                AND latest.station_key = o.station_key
          )
        ORDER BY CASE s.station_key WHEN 'home' THEN 0 ELSE 1 END,
                 s.station_key, o.metric
        """
    ).fetchall()
    grouped: dict[tuple[str, str, str], list[CurrentReading]] = defaultdict(list)
    for station_key, name, observed_at, metric, value, unit in rows:
        grouped[(station_key, name, observed_at)].append(
            CurrentReading(
                metric=metric,
                label=METRIC_LABELS.get(metric, metric.replace("_", " ").title()),
                display_value=current_value(metric, value, unit),
            )
        )
    return tuple(
        CurrentStation(
            key=station_key,
            name=name,
            updated_at=local_observation_time(observed_at),
            stale=observation_is_stale(observed_at),
            readings=tuple(
                sorted(
                    readings,
                    key=lambda reading: CURRENT_METRIC_ORDER.get(reading.metric, 99),
                )
            ),
        )
        for (station_key, name, observed_at), readings in grouped.items()
    )


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


def chart_points(
    points: list[tuple[str, float]], *, daily: bool = False, limit: int = 500
) -> list[tuple[str, float]]:
    """Bound SVG size while retaining the first and last observations."""
    if daily:
        by_date: dict[str, list[float]] = defaultdict(list)
        for observed_at, value in points:
            by_date[observed_at[:10]].append(value)
        points = [
            (observed_at, sum(values) / len(values))
            for observed_at, values in by_date.items()
        ]
    if len(points) <= limit:
        return points
    return [
        points[round(index * (len(points) - 1) / (limit - 1))] for index in range(limit)
    ]


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
    compare_temperatures = len(TEMPERATURE_METRICS.intersection(metrics)) > 1
    chart_keys = {
        metric: (
            "temperature_comparison"
            if compare_temperatures and metric in TEMPERATURE_METRICS
            else metric
        )
        for metric in metrics
    }
    chart_order = tuple(dict.fromkeys(chart_keys[metric] for metric in metrics))
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
        chart_key = chart_keys[metric]
        units[chart_key] = unit
        station_label = f"{station_name} · {source_label(source)}"
        if chart_key == "temperature_comparison":
            station_label = f"{station_label} · {METRIC_LABELS[metric]}"
        grouped[chart_key][station_label].append((observed_at, value))

    charts = []
    for chart_key in chart_order:
        station_values = grouped.get(chart_key)
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
            for observed_at, value in chart_points(
                points, daily=x_span >= 60 * 24 * 60 * 60
            ):
                x = 52 + 926 * ((timestamp(observed_at) - start_timestamp) / x_span)
                y = 18 + 204 * ((maximum - value) / y_span)
                coordinates.append(f"{x:.1f},{y:.1f}")
            series.append(
                ChartSeries(
                    label=station_label,
                    color=COLORS[index % len(COLORS)],
                    points=" ".join(coordinates),
                    coordinates=tuple(
                        tuple(float(number) for number in coordinate.split(","))
                        for coordinate in coordinates
                    ),
                    count=len(points),
                )
            )
        charts.append(
            MetricChart(
                key=chart_key,
                label=(
                    "Temperature comparison"
                    if chart_key == "temperature_comparison"
                    else METRIC_LABELS.get(chart_key, chart_key)
                ),
                unit=units[chart_key],
                minimum=minimum,
                maximum=maximum,
                average=sum(values) / len(values),
                latest=latest,
                latest_date=latest_date,
                series=tuple(series),
            )
        )
    return tuple(charts)

"""Read-only dashboard queries and chart preparation."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

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


def load_options(connection: sqlite3.Connection) -> DashboardOptions:
    bounds = connection.execute(
        "SELECT min(observed_at), max(observed_at) FROM observations"
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
                label=f"{name} · {source.upper()}",
            )
            for source, station_key, name in station_rows
        ),
        metrics=tuple(
            MetricOption(metric, METRIC_LABELS.get(metric, metric), unit)
            for metric, unit in metric_rows
        ),
    )


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
    parameters: list[str] = [start, end]
    for source, station_key in stations:
        parameters.extend((source, station_key))
    parameters.extend(metrics)
    rows = connection.execute(
        f"""
        SELECT o.metric, o.unit, o.observed_at, o.value,
               s.name || ' · ' || upper(s.source) AS station_label
        FROM observations AS o
        JOIN stations AS s
          ON s.source = o.source AND s.station_key = o.station_key
        WHERE o.observed_at BETWEEN ? AND ?
          AND ({station_clause})
          AND o.metric IN ({metric_clause})
        ORDER BY o.metric, station_label, o.observed_at
        """,
        parameters,
    ).fetchall()

    grouped: dict[str, dict[str, list[tuple[str, float]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    units: dict[str, str] = {}
    for metric, unit, observed_at, value, station_label in rows:
        units[metric] = unit
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
        start_ordinal = date.fromisoformat(start).toordinal()
        end_ordinal = date.fromisoformat(end).toordinal()
        x_span = end_ordinal - start_ordinal or 1
        series = []
        latest_date, latest = max(
            (point for points in station_values.values() for point in points),
            key=lambda point: point[0],
        )
        for index, (station_label, points) in enumerate(station_values.items()):
            coordinates = []
            for observed_at, value in points:
                if end_ordinal == start_ordinal:
                    x = 515
                else:
                    x = 52 + 926 * (
                        (date.fromisoformat(observed_at).toordinal() - start_ordinal)
                        / x_span
                    )
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

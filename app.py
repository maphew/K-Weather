#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["flask>=3.1,<4"]
# ///
"""K-Weather read-only dashboard."""

from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path

from flask import Flask, render_template, request

from dashboard import DEFAULT_METRICS, default_start, load_charts, load_options

DEFAULT_DATABASE = Path("yukon_weather/k-weather.sqlite3")


def valid_date(value: str | None, fallback: str) -> str:
    if value:
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            pass
    return fallback


def create_app(database_path: str | Path | None = None) -> Flask:
    app = Flask(__name__)
    app.config["DATABASE"] = str(
        database_path or os.environ.get("K_WEATHER_DB", DEFAULT_DATABASE)
    )

    @app.get("/")
    def dashboard():
        path = Path(app.config["DATABASE"])
        if not path.exists():
            return render_template("dashboard.html", options=None, charts=())

        database = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
        try:
            options = load_options(database)
            if not options.first_date or not options.last_date:
                return render_template("dashboard.html", options=options, charts=())
            start = valid_date(request.args.get("start"), default_start(options) or "")
            end = valid_date(request.args.get("end"), options.last_date)
            if start > end:
                start, end = end, start
            available_stations = tuple(option.key for option in options.stations)
            requested_stations = request.args.getlist("station")
            selected_stations = (
                tuple(
                    value for value in requested_stations if value in available_stations
                )
                or available_stations
            )
            available_metrics = tuple(option.key for option in options.metrics)
            requested_metrics = request.args.getlist("metric")
            selected_metrics = tuple(
                dict.fromkeys(
                    value for value in requested_metrics if value in available_metrics
                )
            ) or tuple(
                metric for metric in DEFAULT_METRICS if metric in available_metrics
            )
            if not selected_metrics:
                selected_metrics = available_metrics[:3]
            charts = load_charts(
                database,
                start=start,
                end=end,
                station_keys=selected_stations,
                metrics=selected_metrics,
            )
            return render_template(
                "dashboard.html",
                options=options,
                charts=charts,
                start=start,
                end=end,
                selected_stations=selected_stations,
                selected_metrics=selected_metrics,
            )
        finally:
            database.close()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))

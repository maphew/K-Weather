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
from functools import wraps
from hmac import compare_digest
from pathlib import Path
from threading import Lock

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from auth import github_actions_refresh_token_valid
from dashboard import (
    DEFAULT_METRICS,
    default_start,
    load_charts,
    load_options,
    load_refresh_status,
)
from refresh import refresh_eccc
from weather_store import connect_database

DEFAULT_DATABASE = Path("yukon_weather/k-weather.sqlite3")


def valid_date(value: str | None, fallback: str) -> str:
    if value:
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            pass
    return fallback


def create_app(
    database_path: str | Path | None = None,
    *,
    username: str | None = None,
    password: str | None = None,
    secret_key: str | None = None,
    refresh_token: str | None = None,
    refresh_token_verifier=github_actions_refresh_token_valid,
    refresher=refresh_eccc,
) -> Flask:
    app = Flask(__name__)
    app.config["DATABASE"] = str(
        database_path or os.environ.get("K_WEATHER_DB", DEFAULT_DATABASE)
    )
    app.config["AUTH_USERNAME"] = username or os.environ.get("K_WEATHER_USERNAME")
    app.config["AUTH_PASSWORD"] = password or os.environ.get("K_WEATHER_PASSWORD")
    app.config["SECRET_KEY"] = secret_key or os.environ.get("K_WEATHER_SECRET_KEY")
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=not app.config["TESTING"],
    )
    app.config["REFRESH_TOKEN"] = refresh_token or os.environ.get(
        "K_WEATHER_REFRESH_TOKEN"
    )
    database = connect_database(app.config["DATABASE"])
    database.close()
    refresh_lock = Lock()

    def configured() -> bool:
        return bool(
            app.config["AUTH_USERNAME"]
            and app.config["AUTH_PASSWORD"]
            and app.config["SECRET_KEY"]
        )

    def dashboard_authenticated() -> bool:
        if session.get("authenticated") is True:
            return True
        authorization = request.authorization
        return bool(
            authorization
            and authorization.type == "basic"
            and compare_digest(
                authorization.username or "", app.config["AUTH_USERNAME"] or ""
            )
            and compare_digest(
                authorization.password or "", app.config["AUTH_PASSWORD"] or ""
            )
        )

    def require_dashboard_auth(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not configured():
                return "K-Weather authentication is not configured\n", 503
            if not dashboard_authenticated():
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.endpoint == "dashboard":
            response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.route("/login", methods=("GET", "POST"))
    def login():
        if not configured():
            return "K-Weather authentication is not configured\n", 503
        error = None
        if request.method == "POST":
            valid_username = compare_digest(
                request.form.get("username", ""), app.config["AUTH_USERNAME"]
            )
            valid_password = compare_digest(
                request.form.get("password", ""), app.config["AUTH_PASSWORD"]
            )
            if valid_username and valid_password:
                session.clear()
                session["authenticated"] = True
                return redirect(url_for("dashboard"))
            error = "That username or password did not match."
        return render_template("login.html", error=error)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/health")
    def health():
        return jsonify(status="ok" if configured() else "misconfigured"), (
            200 if configured() else 503
        )

    @app.get("/")
    @require_dashboard_auth
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
                refresh_status=load_refresh_status(database),
                start=start,
                end=end,
                selected_stations=selected_stations,
                selected_metrics=selected_metrics,
            )
        finally:
            database.close()

    @app.post("/refresh")
    def refresh():
        if not configured():
            return jsonify(error="service is not configured"), 503
        supplied = request.headers.get("Authorization", "")
        token = (
            supplied.removeprefix("Bearer ") if supplied.startswith("Bearer ") else ""
        )
        static_token = app.config["REFRESH_TOKEN"]
        valid_static_token = bool(static_token and compare_digest(token, static_token))
        if not valid_static_token and not refresh_token_verifier(token):
            return jsonify(error="unauthorized"), 401
        if not refresh_lock.acquire(blocking=False):
            return jsonify(error="refresh already running"), 409
        try:
            database = connect_database(app.config["DATABASE"])
            try:
                results = refresher(database)
            finally:
                database.close()
            return jsonify(
                status="completed",
                stations=len(results),
                rows=sum(result.rows_received for result in results),
                observations=sum(result.observations_written for result in results),
            )
        except Exception:
            app.logger.exception("weather refresh failed")
            return jsonify(error="refresh failed"), 502
        finally:
            refresh_lock.release()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))

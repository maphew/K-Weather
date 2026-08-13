# 0005: Use separate dashboard and refresh credentials

Date: 2026-08-13

Status: Accepted

## Context

The Sprite URL must be public at the infrastructure layer so a family member
and an external scheduler can wake it. The dashboard must remain private, and
scheduled refreshes need machine authentication. SQLite supports one writer,
and duplicate scheduler requests can overlap during retries.

## Decision

Protect the dashboard with HTTP Basic authentication over HTTPS, using a shared
household username and generated password. Protect `POST /refresh` with a
short-lived, cryptographically signed GitHub Actions OIDC token restricted to
this repository, workflow, event type, and `main` branch. Configure the
dashboard credential only through Sprite service environment.

Run one Gunicorn worker and serialize refresh calls with a non-blocking process
lock. Return `409` for overlap. Refresh only the current ECCC year, adding the
previous year during January for late corrections. Record batch success or
failure in `refresh_runs`; expose only a generic failure notice in the UI.

Use GitHub Actions cron at minute 17 every six hours as the external wake-up
trigger. GitHub issues a fresh OIDC token for each job, so no long-lived refresh
secret needs to exist in GitHub.

## Consequences

- Browser access presents the standard username/password prompt.
- The dashboard credential can be rotated without changing the scheduler.
- A stolen workflow OIDC token expires quickly and cannot be issued by another
  repository or workflow.
- A single app process is required for the in-process lock to cover all writes.
- Refresh performs three ECCC requests normally and six during January instead
  of downloading the full history every six hours.
- A future multi-process deployment needs a database-backed lock or a different
  storage architecture.

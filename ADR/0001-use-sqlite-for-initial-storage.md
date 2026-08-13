# 0001: Use SQLite for initial application storage

Date: 2026-08-13

Status: Accepted

## Context

K-Weather is a small, family-facing weather archive with one scheduled writer
and a read-heavy dashboard. It needs durable history and idempotent imports but
does not currently need distributed writes or horizontal scaling.

## Decision

Use SQLite for normalized stations, observations, and ingestion-run metadata.
Run one application instance with one writer. Ingestion must enforce a unique
observation identity so repeated six-hour refreshes are safe.

## Consequences

- Development and backup remain simple, with the entire database in one file.
- The deployment must provide a durable filesystem.
- Multiple application writers or replicas must not share the SQLite file.
- Revisit this choice if concurrent writers or horizontal scaling become real
  requirements rather than anticipated ones.

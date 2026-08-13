# 0009: Import private MyAcuRite history at full resolution

Date: 2026-08-13

Status: Accepted

## Context

Six-hour cloud polling captures only new snapshots. MyAcuRite's emailed export
contains the available rolling 31-day history for all linked devices at roughly
five-minute resolution. The export filename and contents include household-
linked information and must not enter the public repository.

Rendering every retained point directly would make the server-generated SVG
and HTML unnecessarily large.

## Decision

Import the private CSV directly into normalized observations with interval
`five_minute`. Match the Iris by sensor type and auxiliary sensors by their
existing private display names; reject unknown names rather than risk joining
one household sensor to another. Convert local Whitehorse timestamps to UTC,
preserve all populated measurement columns, and use the existing unique key for
idempotent re-imports.

Keep the raw CSV under ignored private runtime storage and transfer it directly
to the Sprite when importing production. Never commit its filename or contents.

Retain every observation in SQLite, but cap each rendered chart series at 500
evenly sampled points while retaining first and last values. Summary statistics
and observation counts continue to use the complete selected dataset.

## Consequences

- K-Weather preserves the full available pre-activation history for all three
  household devices.
- Re-importing the same export updates rather than duplicates observations.
- Historical charts remain bounded in response size while raw data stays
  available for future analysis and exports.
- Future MyAcuRite schema changes fail explicitly and require a reviewed mapping.

# 0006: Capture MyAcuRite snapshots through its private API

Date: 2026-08-13

Status: Accepted

## Context

The household AcuRite Iris uploads observations to MyAcuRite, which retains
only 31 days of chart history. MyAcuRite does not offer a documented public API.
Its web application uses a private API that can authenticate an account and
return the current dashboard snapshot. The snapshot contains account-linked
identifiers and precise location metadata as well as sensor readings.

A six-hour polling interval cannot reconstruct the existing 31-day history and
will retain only four snapshots per day going forward. Direct local capture
through Acuparse remains a possible higher-frequency future source.

## Decision

Use a narrow private-API client to fetch the latest dashboard snapshot during
the existing protected six-hour refresh. Read the account email and password
only from private environment configuration. Discover account and hub IDs after
login, retain the token and identifiers only in process memory, and never log
request payloads, account-scoped URLs, raw responses, coordinates, or upstream
exception details.

Store only normalized sensor values under the public-safe station identity
`Riverdale household station`. Use the device check-in time as the idempotency
key, normalize it to UTC, skip null sensor values, preserve unknown sensor
names through generic normalization, and retry authentication once after an
HTTP 401.

Preserve the current rolling history separately through a private manual CSV
export and importer after its real schema is available. Do not guess that
schema or commit the export.

## Consequences

- The existing GitHub Actions job captures one current snapshot every six
  hours once production secrets are configured.
- Existing history still requires an immediate manual export before it ages
  out of MyAcuRite.
- An upstream API or response-schema change can stop household capture without
  warning. Existing observations and ECCC history remain available.
- A failed household fetch marks the refresh failed but records only a generic,
  privacy-safe reason.
- The household station appears in the existing date, station, and metric
  filters without exposing its exact location or account identifiers.
- Acuparse remains the preferred fallback if private cloud polling becomes
  unreliable or six-hour resolution becomes insufficient.

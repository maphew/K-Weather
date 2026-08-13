# 0011: Capture recent MyAcuRite five-minute summaries

Date: 2026-08-13

Status: Accepted

## Context

One current MyAcuRite snapshot every six hours loses the readings uploaded
between refreshes. The private dashboard supplies an account-linked hourly
summary URL for each device. The same transient device path provides daily
five-minute summary files, whose values use generic sensor channels also
described by the dashboard response.

## Decision

During every authenticated refresh, derive each device's five-minute summary
location only in process memory. Fetch the dashboard date and the prior two
dates, giving a 48-hour repair overlap for late uploads and interrupted runs.
Accept summary files only from the exact HTTPS `dataapi.myacurite.com` host and
derive only the collection name and date; never persist or log the private URL
or device-path component.

Map generic dashboard channels to the already normalized metric and preferred
display unit. Store each timestamp with interval `five_minute` through the
existing unique observation identity, so repeated overlap updates rather than
duplicates data. A missing daily file is harmless; malformed responses or
other upstream failures fail the refresh with a sanitized error.

Keep the current snapshot ingestion for current-condition cards and as a
fallback indication of the latest device state.

## Consequences

- A six-hour schedule now preserves the intervening five-minute cloud readings
  rather than only four points per day.
- Re-fetching three dates costs nine small files per run for three devices and
  repairs late data without a cursor table or schema expansion.
- The private API remains unsupported and can change without notice. Existing
  data and encrypted backups remain usable if capture stops.
- Direct local Acuparse capture remains the fallback if MyAcuRite removes the
  summary files or stronger independence from its cloud is required.

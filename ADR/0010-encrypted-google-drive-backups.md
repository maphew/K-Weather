# 0010: Keep encrypted, verified backups in Google Drive

Date: 2026-08-13

Status: Accepted

## Context

The Sprite filesystem is persistent but is still one failure domain. The
household archive includes location-sensitive observations and must not be
uploaded to consumer cloud storage as a plain SQLite database or raw CSV.
Copying an active SQLite database and its WAL files is not a reliable snapshot.

## Decision

After each successful six-hour refresh, use SQLite's online backup API to make
a consistent temporary snapshot. Back it up with Restic to a private Google
Drive folder reached through rclone. Restic encrypts data and metadata before
upload, deduplicates snapshots, and supplies versioned recovery points.

Keep the last 14 snapshots, 30 daily snapshots, 52 weekly snapshots, and 1,200
monthly snapshots (100 years, effectively the application's lifetime). Check
the repository after each backup, restore its latest
snapshot into temporary storage, run SQLite `PRAGMA integrity_check`, and
compare the observation count and newest observation timestamp with the source
snapshot. Delete all temporary plaintext copies on success or failure.

Keep the rclone OAuth token and Restic password only in mode-0600 files on the
Sprite. Never upload raw exports unencrypted or place OAuth tokens, passwords,
Drive identifiers, database contents, or account-linked metadata in Git or
logs. A backup failure must fail the scheduled workflow without undoing a
successful weather refresh.

## Consequences

- Sprite loss can be recovered from an independently hosted, versioned archive.
- Google Drive can see encrypted object sizes and timing, but not weather data,
  filenames, or Restic metadata.
- Losing the Restic password makes every backup unrecoverable; it needs a
  separate private household copy.
- The GitHub schedule remains the external wake-up mechanism, but refresh and
  backup have separate authenticated HTTP operations and failure reporting.
- A full repository check, prune, and restore every six hours favors confidence
  over minimum bandwidth; revisit if repository growth makes this burdensome.

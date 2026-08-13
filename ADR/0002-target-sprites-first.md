# 0002: Target Sprites.dev before Fly.io

Date: 2026-08-13

Status: Accepted

## Context

The dashboard should remain available to a family member without requiring a
home server connection. The application needs persistent storage and a refresh
every six hours. Sprites persist their filesystem and wake on HTTP access, but
hibernation stops running processes. Fly.io supports a conventional persistent
Machine and cron process but requires more deployment plumbing.

## Decision

Deploy the first working version to Sprites.dev with:

- SQLite on the persistent Sprite filesystem;
- a Sprite Service that starts the web application after wake-up;
- application-level authentication if the Sprite URL is public; and
- an external scheduler calling an authenticated, idempotent refresh endpoint
  every six hours.

Use Fly.io as the fallback if external scheduling or Sprite operations prove
unreliable or awkward.

## Consequences

- An in-process scheduler is insufficient because it stops during hibernation.
- The refresh endpoint must be protected, observable, and safe to retry.
- Public URL obscurity is not an authentication mechanism.
- A Fly.io migration can retain SQLite only with one Machine and one persistent
  volume writer; otherwise the storage decision must also be revisited.

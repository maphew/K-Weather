# 0003: Keep code public and household operations private

Date: 2026-08-13

Status: Accepted

## Context

K-Weather benefits from a public GitHub repository, while its eventual AcuRite
integration involves a household weather station, account credentials,
account-linked device identifiers, and observations that could reveal a
street-level location. Obfuscation in source control is reversible and does not
protect secrets.

Environment Canada station identifiers and regional observations are already
public. The acceptable public household location is the neighbourhood:
Riverdale, Whitehorse.

## Decision

Keep application source, schema, tests, and deployment templates public. Never
commit:

- credentials, tokens, cookies, or authenticated request captures;
- AcuRite account-linked hub or device identifiers;
- raw or derived household-station exports;
- application databases or backups; or
- household coordinates, addresses, or other street-level location details.

Store credentials in local environment files and hosting secret stores. Keep
operational data in private persistent storage. Public dashboard labels may say
`Riverdale, Whitehorse` but must not expose a more precise household location.
Public ECCC station metadata may retain its official identifiers, though the UI
should avoid coordinates unless the product genuinely needs them.

Before every public push, inspect tracked files and staged changes for secrets
and private identifiers. If private material enters published Git history,
rotate affected credentials and purge the history; deleting it in a later
commit is not sufficient.

## Consequences

- A `.env.example` may document variable names but never real values.
- `.env*`, SQLite files, CSV exports, and generated data are ignored by default.
- Fixtures must be synthetic or public ECCC data, not household observations.
- Deployments require separately configured secrets and private data storage.
- The public repository can be cloned and developed without access to the
  household AcuRite account.

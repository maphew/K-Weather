<!-- BEGIN swamp managed section - DO NOT EDIT -->
# Swamp

This repository is managed with [swamp](https://github.com/swamp-club/swamp).

## Rules

1. **Search before you build.** When automating AWS, APIs, or any external service: (a) search community extensions with `swamp extension search <query>` — prefer `@swamp/*` official extensions first, (b) search local/installed types with `swamp behavior type search <query>`, (c) if a community extension exists, install it with `swamp extension pull <package>` instead of building from scratch, (d) extend an existing type if it covers the domain but lacks the method you need, (e) only create a custom extension behavior in `extensions/models/` as a last resort. Use the `swamp` skill for guidance. The `command/shell` behavior is ONLY for ad-hoc one-off shell commands, NEVER for wrapping CLI tools or building integrations.
2. **Extend, don't be clever.** When a behavior covers the domain but lacks the method you need, extend it with `export const extension` — don't bypass it with shell scripts, CLI tools, or multi-step hacks. One method, one purpose. Use `swamp behavior type describe <type> --json` to check available methods.
3. **Use the data model.** Once data exists in a behavior (via `lookup`, `start`, `sync`, etc.), reference it with CEL expressions. Don't re-fetch data that's already available.
4. **CEL expressions everywhere.** Wire behaviors together with CEL expressions. Always prefer `data.latest("<name>", "<dataName>").attributes.<field>` over the deprecated `model.<name>.resource.<spec>.<instance>.attributes.<field>` pattern.
5. **Verify before destructive operations.** Always `swamp behavior get <name> --json` and verify resource IDs before running delete/stop/destroy methods.
6. **Prefer fan-out methods over loops.** When operating on multiple targets, use a single method that handles all targets internally (factory pattern) rather than looping N separate `swamp behavior run` calls against the same behavior. Multiple parallel calls against the same behavior contend on the per-behavior lock, causing timeouts. A single fan-out method acquires the lock once and produces all outputs in one execution. Check `swamp behavior type describe` for methods that accept filters or produce multiple outputs.
7. **Extension npm deps are bundled; pin them.** Swamp's bundler inlines all npm packages (except zod) into extension bundles at bundle time. When the extension has a `deno.json`, the `deno.lock` beside it decides which versions are bundled; otherwise the registry's current release does. Always pin explicit versions in `npm:` and `jsr:` import specifiers (e.g., `npm:lodash-es@4.17.21`) — `swamp extension push` warns on unpinned and range specifiers.
8. **Reports for reusable data pipelines.** When the task involves building a repeatable pipeline to transform, aggregate, or analyze behavior output (security reports, cost analysis, compliance checks, summaries), create a report extension. Use the `swamp` skill for guidance.
9. **"Workflow" means a swamp workflow.** In this repository the word "workflow" (and "create/run/execute/validate/debug workflow", "automate", "orchestrate", "automated/nightly job") refers to a swamp workflow — a declarative YAML DAG of behavior-method steps authored via `swamp workflow create`. Load and follow the `swamp` skill for these requests. Do NOT interpret these as a request to build an agent task list, spin up worktrees, or schedule a cron/remote agent. Only use those orchestration mechanisms when the user explicitly names one (e.g. "task list", "subagent", "worktree", "cron", "remote agent") or explicitly asks you to do the work yourself step by step rather than author a swamp workflow.
10. **Use swamp, don't bypass it.** Always work through swamp commands — don't go around them with raw shell tools. Use `swamp data query` to find data, not `grep`/`find` on `.swamp/` files. Use behavior methods to interact with resources, not `curl`/`aws`/`gcloud`/`kubectl` when a behavior type already wraps that API — check with `swamp behavior type search`. Use `swamp help` for CLI discovery, not guesswork. Composing with swamp output is fine (e.g. piping `--json` through `jq`) — the anti-pattern is bypassing swamp entirely.
11. **Inspect reports after failures.** When a behavior method or workflow run fails, inspect its generated reports before retrying or changing definitions. Reports run even on failure and capture structured diagnostics — error messages, execution status, arguments, and data output pointers. Use `swamp report get @swamp/method-summary --model <model> --json` for method failures or `swamp report get @swamp/workflow-summary --workflow <workflow> --json` for workflow failures. Run `swamp help report get` to confirm current retrieval syntax.

## Skills

**IMPORTANT:** Always load swamp skills, even when in plan mode. The skills provide
essential context for working with this repository.

- `swamp` - Swamp CLI — behaviors, workflows, data, vaults, extensions, publishing, repos, reports, issues, and troubleshooting
- `swamp-getting-started` - Interactive onboarding for new swamp users

## Getting Started

If you were asked to read a task brief under `tasks/` (a file whose first
line is `<!-- swamp start brief v1 -->`), read that brief, then invoke the
`swamp-getting-started` skill and follow it from its brief entry point.

If the user is new to swamp or asks to get started, or a swamp command you
run shows this repository has no behaviors yet, invoke the
`swamp-getting-started` skill. It checks for existing behaviors itself and walks
new users through an interactive onboarding tutorial.

Otherwise, use the `swamp` skill to work with swamp behaviors.

## Commands

Use `swamp --help` to see available commands. For a machine-readable JSON
schema of the CLI (commands, options, arguments) intended for agent
consumption, run `swamp help [<command>...]` — e.g. `swamp help` returns
the full tree, and `swamp help behavior run` scopes to a subtree.

Behaviors (formerly models) are managed with `swamp behavior` — e.g.
`swamp behavior run <name> <method>` (or
`swamp behavior run @<type> <method> <name>` to run against a type
directly). Every `swamp model …` spelling remains supported.
<!-- END swamp managed section -->

# K-Weather

Persistent weather history and a family-friendly dashboard for Riverdale,
Whitehorse, YT. Two sources, two time horizons.

## Context

The household has an **AcuRite Iris** weather station. The goal is to own the
data locally and analyse it without publishing account-linked identifiers or a
street-level location.

Two findings that shaped this:

1. **MyAcuRite retains only 31 days.** The `/timespans/alltime` and
   `/timespans/year` URL fragments are client-side routing only — the backend
   has nothing older. Anything before ~31 days ago is permanently gone. The
   page itself admits this: *"Charting is only available for up to the previous
   31 days."*
2. **So historical context has to come from Environment Canada**, and
   go-forward AcuRite data has to be captured locally before it rolls off.

## Current state

- `get_yukon_weather.py` — pulls ECCC **daily** data from 2020 through the
  current year.
  Runnable as-is: `uv run get_yukon_weather.py`. Writes to `./yukon_weather/`.
- Live endpoint verification on 2026-08-13 confirmed that station 50842 has
  current observations. Stations 1618 and 1617 respond but currently contain
  blank calendar rows; the script now discards those placeholders.
- `weather_store.py` owns the normalized SQLite schema and idempotent ECCC
  ingestion. The downloader writes private runtime data to
  `yukon_weather/k-weather.sqlite3`.
- `test_weather_store.py` covers duplicate refreshes, blank observations,
  failed-run metadata, and station fallback.
- `app.py`, `dashboard.py`, and `templates/dashboard.html` provide the
  read-only Flask dashboard with server-rendered SVG charts and linkable date,
  station, and metric filters. See ADR 0004.
- `test_dashboard.py` covers empty, single-series, multi-metric, and location
  privacy states.
- Dashboard access uses a mobile-friendly login form and secret-configured
  signed session cookie. Scheduled refresh uses a repository/workflow-bound
  GitHub Actions OIDC token; no static scheduler credential is stored. Refresh
  is incremental, single-writer, and recorded in `refresh_runs`. See ADR 0005.
- `.github/workflows/refresh.yml` triggers refresh at minute 17 every six hours.

## Stations

| Key | Name | ECCC station ID | Notes |
|---|---|---|---|
| `riverdale` | WHITEHORSE RIVERDALE | 1618 | Climate ID 2101400. Co-op site; current daily responses are blank. Preferred when observations exist. |
| `whitehorse_a` | WHITEHORSE A | 50842 | Climate ID 2101303. Current airport station and active fallback. |
| `whitehorse_a_legacy` | WHITEHORSE A | 1617 | Climate ID 2101300. Legacy airport record. |

Station IDs are ECCC's *internal* numeric IDs, not the 7-digit Climate ID.
Verify at <https://climate.weather.gc.ca/historical_data/search_historic_data_e.html>.

## ECCC bulk endpoint

```
https://climate.weather.gc.ca/climate_data/bulk_data_e.html
  ?format=csv
  &stationID=<internal ID>
  &Year=<YYYY>&Month=1&Day=1
  &timeframe=2          # 1=hourly, 2=daily, 3=monthly
  &submit=Download+Data
```

One year per request for daily; one *month* per request for hourly
(`timeframe=1` ignores nothing but returns a single month — `Month` matters
there). Public, no auth, no documented rate limit — script sleeps 1s anyway.

Licence: Open Government Licence – Canada. Free to redistribute.

## Product direction

The desired product is an always-addressable dashboard that a non-technical
family member can browse and filter. Weather data should refresh every six
hours and remain queryable indefinitely.

Prefer a small Python web app with SQLite as the first implementation. Keep
ingestion idempotent with a unique key based on source, station, timestamp,
and observation type so scheduled refreshes can safely overlap.

Target **Sprites.dev** first:

- Its persistent filesystem suits a single-node SQLite app.
- A Sprite URL wakes the service on demand, and a Sprite Service restarts the
  dashboard after hibernation.
- Hibernation stops processes, so an in-process scheduler alone cannot
  guarantee six-hour refreshes. Use an external scheduler to call a protected,
  idempotent refresh endpoint every six hours.
- Sprite URLs are private by default. If made public for family access, add
  application authentication; do not rely on the URL being hard to guess.

**Fly.io** is the fallback if conventional production operations matter more
than minimal setup. Use one web Machine, a persistent volume for SQLite, and
Supercronic or Cron Manager for the six-hour job. Do not run multiple writers
against a single SQLite volume.

## Resume order

1. Run and inspect the corrected historical importer.
2. Define a normalized SQLite schema and idempotent ECCC upsert.
3. Add the read-only dashboard with date, station/source, and metric filters.
4. Add a protected refresh command/endpoint and six-hour scheduling.
5. Import the manually exported current MyAcuRite CSV.
6. Deploy to a Sprite with app-level authentication; evaluate Fly.io only if
   Sprite scheduling or operations prove awkward.
7. Separately stand up **Acuparse** (<https://docs.acuparse.com/>) on private
   household infrastructure for direct AcuRite capture. It captures forward
   only and does not replace exporting the current rolling 31-day MyAcuRite
   window now.

## Conventions

Lazy repo — minimal README, no CI, no test suite unless something earns one.
Script is uv-inline-metadata style, single file, stdlib + requests + pandas.

`current.md` is the cold-start handoff and the first file a new development
session should read. Update it whenever completed work, verification evidence,
the immediate next job, or a material blocker changes. Keep it concise and
current; durable architectural decisions and their rationale belong in `ADR/`.

This repository is public. Follow `ADR/0003-public-code-private-operations.md`:
never commit credentials, account-linked device/hub IDs, raw household weather
exports, databases, or street-level location data. Public UI copy may identify
the location as Riverdale, Whitehorse, but no more precisely. Application
runtime secrets belong in local environment files or hosting secret stores,
not obfuscated in source. GitHub developer credentials are not runtime secrets:
keep remotes on SSH and store a fresh, rotated PAT in Swamp's local `default`
vault under `GITHUB_PAT`. The refresh workflow continues to use repository-bound
GitHub Actions OIDC; it must not consume this PAT.

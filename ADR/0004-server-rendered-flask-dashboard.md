# 0004: Use Flask with server-rendered SVG charts

Date: 2026-08-13

Status: Accepted

## Context

K-Weather needs a small read-only dashboard over one SQLite database. The
initial audience is a household, and the interface should remain quick to load
after a Sprite wakes. A client-side chart framework would add another runtime
dependency and could leave the dashboard blank when a third-party CDN fails.

## Decision

Use Flask for HTTP routing and Jinja templates. Query SQLite read-only and
render charts as accessible inline SVG on the server. Use ordinary GET form
parameters for date, station, and metric filters so filtered views remain
linkable and work without JavaScript.

## Consequences

- The first response contains complete charts with no browser-side data fetch.
- The app has one small runtime dependency and no frontend build step.
- SVG lines intentionally favor broad historical patterns over interactive
  tooltips; add progressive enhancement later only if it earns its complexity.
- Authentication can wrap the Flask application before public deployment.

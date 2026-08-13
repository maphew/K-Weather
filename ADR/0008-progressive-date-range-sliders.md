# 0008: Add progressive date-range sliders

Date: 2026-08-13

Status: Accepted

## Context

The historical dashboard's browser date pickers were precise but cumbersome
for exploring a multi-year archive. AcuRite observations were technically in
the shared query but were easy to miss because household temperature was not a
default metric and a single snapshot produced an invisible SVG polyline.

## Decision

Keep editable native date fields as the source submitted to the server. Add two
small range sliders that synchronize with those fields in both directions and
prevent the start handle from passing the end handle. Treat the enhancement as
optional: without JavaScript, typed/native date entry and ordinary GET links
continue to work.

Apply one history range to every selected source and station. Include household
temperature in the default charts, and render SVG point markers for series with
24 or fewer observations so isolated AcuRite snapshots remain visible.
Combine selected ECCC daily high/mean/low and AcuRite temperature series in one
temperature-comparison chart so source differences are immediately apparent.

Current-condition cards continue to mean the latest available readings and are
therefore independent of the historical range.

## Consequences

- Broad time ranges can be explored quickly without sacrificing exact dates.
- URLs continue to contain only `start` and `end` dates and remain shareable.
- ECCC and AcuRite history use the same server-side range predicate.
- The dashboard now has a small first-party JavaScript enhancement but retains
  complete non-JavaScript behavior.

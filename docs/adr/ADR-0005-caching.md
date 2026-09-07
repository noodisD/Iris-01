# ADR-0005: Cache only where there is a reader, and never without expiry

## Status
Accepted — 2026-09-07

## Context
Two engines had contradictory caching models. Resolution read `pattern_resolutions`
and treated any non-null `last_computed_at` as fresh — so a verdict computed
years ago would still be served, which is meaningless for an engine that
compares a rolling recent window against a rolling baseline: a theme goes quiet
and becomes "dissipated" by the calendar alone, with no new data. Trajectory
wrote `theme_trajectories` on every analysis and nothing anywhere read it.

## Decision
A cache exists only where something reads it, and every cached value has an
expiry. Resolution keeps its cache with a 24-hour TTL — the granularity at which
its windows actually move. Trajectory has no cache and always recomputes.

Pairwise engines (leverage, decision impact) are the exception in shape, not in
principle: they are O(themes²) and do not cache on read, so their results are
recomputed at ingest — where an occurrence has just changed the theme graph —
and the chat path reads those rows. Recomputing them per chat turn would put an
O(n²) scan on the path where the user is waiting.

## Consequences
No analytical answer can outlive the question it answered. Adding a cache
requires naming its reader and its expiry.

`theme_trajectories` remains as an empty table until there is a migration tool
to drop it, which is recorded here so the next reader knows it is deliberate
rather than forgotten.

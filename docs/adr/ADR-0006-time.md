# ADR-0006: UTC instants for analysis, local calendar days for habits

## Status
Accepted — 2026-09-06

## Context
Every timestamp column is `TIMESTAMPTZ`, so psycopg2 returns aware UTC. The
engines stripped that offset and compared the result against a naive
`datetime.now()` — local time. Every sliding window was therefore displaced by
the host's UTC offset: measured at exactly two hours in CEST, one in CET.

That was not cosmetic. With occurrences either side of the 21-day resolution
edge, the same data classified as `persisting` (recent=2) correctly and
`dissipated` (recent=0) with the displacement — the opposite conclusion, and one
that would flip twice a year at daylight-saving transitions.

## Decision
All analytical comparisons use timezone-aware UTC, through `agent/timeutils.py`:
`utc_now()` for the present moment and `to_utc()` for anything read from the
database or parsed from a string.

Habit tracking deliberately keeps `date.today()`. A habit day is a human
calendar day: a tick at 23:30 local belongs to today, not to tomorrow in UTC.

## Consequences
Analytical output no longer depends on where the machine is or the time of year;
`tests/test_timezone_invariance.py` enforces this by classifying the same data
under `TZ=UTC` and `TZ=Europe/Warsaw`.

The two rules must not be confused. Ruff's `DTZ` findings in the habit trackers
are correct as they stand, and "fixing" them would be a regression: the engines
compare *instants* and need UTC, the trackers record *days* and need the local
calendar.

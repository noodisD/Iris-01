# resources.telemetry

**What it means:** Telemetry is growing faster or larger than expected.

**Confirm:** `SELECT name, count(*) FROM obs_spans WHERE started_at > NOW() - interval '1 day' GROUP BY 1 ORDER BY 2 DESC LIMIT 10`.

**Safe fix:** Prune old rows and `VACUUM FULL obs_spans` (safe-auto); fix the span name that grew.

**Never:** Never drop obs_* tables: the Observatory and the doctor read them.

See [README](README.md) for action classes and the rules every check follows.

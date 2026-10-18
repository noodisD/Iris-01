# patterns.progress

**What it means:** The pattern update failed, was cut short repeatedly, or has run unusually long.

**Confirm:** `SELECT stage, updated_at, error_kind FROM discovery_state`; `SELECT attempts FROM processing_queue WHERE source_type = 'personal_dynamics'`.

**Safe fix:** Failed: read the journal, fix, re-queue once (safe-auto). Many attempts: stop restarting and let it finish.

**Never:** Do not queue re-reads while it runs unless they are wanted: each one makes the running update out of date.

See [README](README.md) for action classes and the rules every check follows.

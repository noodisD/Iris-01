-- 0054_health_fixes.sql
--
-- What the doctor repaired on its own (agent/doctor/fixes.py): only actions its
-- checks class as safe-auto, each re-checked afterwards. Kept so a repair is
-- never silent, and so a failed job is re-queued once, not every morning.
-- Counts and ids only.

CREATE TABLE health_fixes (
    id        SERIAL PRIMARY KEY,
    run_id    UUID,
    fixed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    check_id  TEXT NOT NULL,
    outcome   TEXT NOT NULL CHECK (outcome IN ('fixed', 'partly', 'unchanged', 'failed')),
    summary   TEXT NOT NULL,
    details   JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX health_fixes_check ON health_fixes (check_id, fixed_at DESC);

-- 0053_health_checks.sql
--
-- Each run of the doctor (agent/doctor) keeps one row per check, so a later run
-- can say what changed: a check that newly fails, one that got worse, one that
-- recovered. Counts, timings and ids only; never what anyone wrote.

CREATE TABLE health_checks (
    id        SERIAL PRIMARY KEY,
    run_id    UUID NOT NULL,
    run_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    check_id  TEXT NOT NULL,
    status    TEXT NOT NULL CHECK (status IN ('ok', 'warn', 'fail', 'waiting', 'unknown')),
    value     DOUBLE PRECISION,
    details   JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX health_checks_check ON health_checks (check_id, run_at DESC);
CREATE INDEX health_checks_run ON health_checks (run_id);

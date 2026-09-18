-- 0010_observation_runs.sql
--
-- What a reading run read, and what it produced before merging.
--
-- An independent review asked how many raw observations preceded consolidation
-- on the historical run. The answer could not be given: nothing recorded it. The
-- merge's behaviour could only be inferred from its output, and the review noted
-- that this "prevents assigning every undesirable final candidate specifically
-- to consolidation rather than an initial extraction error; both mechanisms need
-- testing".
--
-- A run record fixes three things at once:
--
--   * Consolidation becomes evaluable without paying for another read of the
--     owner's private archive. The raw observations are kept, so a change to
--     merging can be replayed against them offline.
--   * A partial read stops looking like a complete one. Passes that failed are
--     recorded, so "nothing found" and "half of it never ran" are distinguishable.
--   * Re-running discovery stops resurrecting decisions. A proposal the owner
--     already rejected can be recognised and not offered again.
--
-- `raw_observations` holds pre-merge output as JSONB: claims and their verified
-- citations, exactly as they came back, before anything was joined. That is the
-- owner's own writing, so it lives in their own database and goes nowhere else.

CREATE TABLE IF NOT EXISTS observation_runs (
    id                SERIAL PRIMARY KEY,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at       TIMESTAMPTZ,
    -- 'complete' when every pass returned; 'partial' when some failed; 'failed'
    -- when none did. Never inferred from the number of findings.
    status            VARCHAR(16) NOT NULL DEFAULT 'running',
    model             VARCHAR(64),
    prompt_version    VARCHAR(32),
    entries_read      INTEGER NOT NULL DEFAULT 0,
    passes_planned    INTEGER NOT NULL DEFAULT 0,
    passes_completed  INTEGER NOT NULL DEFAULT 0,
    raw_observations  JSONB,
    candidates_staged INTEGER NOT NULL DEFAULT 0,
    error             TEXT
);

CREATE INDEX IF NOT EXISTS idx_observation_runs_user ON observation_runs(user_id, started_at DESC);

-- Which run proposed a construct, so a candidate can be traced back to the
-- reading that produced it, and so a rerun can tell old proposals from new ones.
ALTER TABLE themes ADD COLUMN IF NOT EXISTS observation_run_id INTEGER
    REFERENCES observation_runs(id) ON DELETE SET NULL;

-- A stable identity for "this same proposal", so re-reading unchanged writing
-- does not offer the owner a decision they have already made. Derived from the
-- claim and the citations that support it, not from the row id.
ALTER TABLE themes ADD COLUMN IF NOT EXISTS proposal_key VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_themes_proposal_key ON themes(user_id, proposal_key);

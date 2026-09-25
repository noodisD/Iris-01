-- 0032_difference_verdicts.sql
--
-- Insights, as differences in outcome. For a pattern, the occasions that went
-- better and those that went worse are compared by what else was true on each
-- side; a pattern that sits on one side and not the other is a difference, and
-- each such difference is an insight on the Insights screen. It is a difference
-- between two sets of occasions, never a cause, so what it means is the owner's
-- to say, and this records that: whether it rings true, per pair of patterns.
--
-- The differences themselves are arithmetic over pattern_labels and are not
-- stored. A verdict outlives a difference that later disappears, so reloading
-- a reading cannot erase what the owner said.
CREATE TABLE IF NOT EXISTS difference_verdicts (
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pattern_id        VARCHAR(64) NOT NULL,
    other_pattern_id  VARCHAR(64) NOT NULL,
    verdict           VARCHAR(12) NOT NULL CHECK (verdict IN ('rings_true', 'does_not', 'unsure')),
    note              TEXT,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, pattern_id, other_pattern_id)
);

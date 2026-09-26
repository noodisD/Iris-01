-- 0037_day_difference_verdicts.sql
-- Comparisons are computed from measured days; only the owner's answer persists.
-- A verdict remains when a comparison later falls below its display threshold.

CREATE TABLE day_difference_verdicts (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    outcome     TEXT NOT NULL CHECK (outcome IN
                ('energy', 'mood', 'sleep_quality', 'stress', 'focus')),
    split       TEXT NOT NULL CHECK (split IN
                ('office_home', 'commute', 'steps', 'screen_time', 'social_share', 'sleep')),
    verdict     VARCHAR(12) NOT NULL CHECK (verdict IN ('rings_true', 'does_not', 'unsure')),
    note        TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, outcome, split)
);

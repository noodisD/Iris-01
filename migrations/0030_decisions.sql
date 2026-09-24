-- 0030_decisions.sql
--
-- A log of risky commitments, written at the moment one is made.
--
-- Looking back through the archive could not say when the owner commits more
-- than they can take back, because the facts that would answer it were almost
-- never written down: how much of what they had was at stake, whether any of
-- it was borrowed, what the days before held, whether money was needed for
-- something soon, how they had slept. Of fourteen such occasions found in the
-- writing, money pressure was stated once and tiredness never. This records
-- exactly those things at the time, and the outcome later.
--
-- Every commitment belongs here, not only the large ones. Without the ordinary
-- ones there is nothing to compare the large ones against.
--
-- Numbered 0030, not 0017: another branch owns 0017-0020 and the live database
-- already has them applied. The runner allows a gap; it refuses a collision.
CREATE TABLE IF NOT EXISTS decisions (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    decided_on       DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    what             TEXT NOT NULL CHECK (length(btrim(what)) > 0),
    -- Share of what the owner had, as a percentage. Above 100 is possible and
    -- is exactly the case worth seeing, so there is no upper bound.
    share_pct        NUMERIC(7,2) CHECK (share_pct >= 0),
    borrowed         BOOLEAN NOT NULL DEFAULT FALSE,
    last_days        VARCHAR(12) CHECK (last_days IN ('big_loss', 'big_win', 'neither')),
    money_needed_for TEXT,
    money_needed_by  DATE,
    sleep_hours      NUMERIC(3,1) CHECK (sleep_hours >= 0 AND sleep_hours <= 24),
    energy           SMALLINT CHECK (energy BETWEEN 1 AND 10),
    plan             TEXT,
    outcome          TEXT,
    followed_plan    VARCHAR(8) CHECK (followed_plan IN ('yes', 'partly', 'no')),
    closed_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS decisions_user_day
    ON decisions (user_id, decided_on DESC, id DESC);

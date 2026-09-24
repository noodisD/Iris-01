-- 0030_decisions.sql
--
-- A decision journal, written at the moment a decision is made.
--
-- Looking back through the archive could not say when the owner commits more
-- than they can take back, because the facts that would answer it were almost
-- never written down: how much was at stake and whether it could be undone,
-- what the days before held, what was pushing for a decision, how they had
-- slept and felt. Of fourteen such occasions found in the writing, pressure
-- was stated once and tiredness never. This records those things at the time,
-- for any kind of decision, and the outcome later.
--
-- Every decision belongs here, not only the large ones. Without the ordinary
-- ones there is nothing to compare the large ones against.
--
-- `stake` and `reversible` together are the library pattern "committed more
-- than could be taken back", asked directly instead of inferred afterwards.
-- `would_repeat` is kept apart from `outcome` on purpose: a good decision can
-- turn out badly and a bad one well, and only the owner's judgement of the
-- decision itself separates the two.
--
-- Numbered 0030, not 0017: another branch owns 0017-0020 and the live database
-- already has them applied. The runner allows a gap; it refuses a collision.
CREATE TABLE IF NOT EXISTS decisions (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    decided_on      DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    what            TEXT NOT NULL CHECK (length(btrim(what)) > 0),
    stake           VARCHAR(16) CHECK (stake IN ('little', 'fair', 'a_lot', 'beyond_means')),
    reversible      VARCHAR(12) CHECK (reversible IN ('easily', 'at_a_cost', 'not_at_all')),
    confidence      SMALLINT CHECK (confidence BETWEEN 0 AND 100),
    last_days       VARCHAR(12) CHECK (last_days IN ('setback', 'success', 'neither')),
    pressures       TEXT[] NOT NULL DEFAULT '{}'
                    CHECK (pressures <@ ARRAY['deadline', 'money', 'people', 'urge']::TEXT[]),
    sleep_hours     NUMERIC(3,1) CHECK (sleep_hours >= 0 AND sleep_hours <= 24),
    energy          SMALLINT CHECK (energy BETWEEN 1 AND 10),
    feeling         VARCHAR(12) CHECK (feeling IN ('calm', 'excited', 'anxious', 'frustrated')),
    plan            TEXT,
    outcome         TEXT,
    followed_plan   VARCHAR(8) CHECK (followed_plan IN ('yes', 'partly', 'no')),
    would_repeat    VARCHAR(8) CHECK (would_repeat IN ('yes', 'no', 'unsure')),
    closed_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS decisions_user_day
    ON decisions (user_id, decided_on DESC, id DESC);

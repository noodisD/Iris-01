-- 0031_occasions_and_patterns.sql
--
-- Discovery, brought into the app.
--
-- An occasion is one account the reader found in the owner's writing: who, what
-- was going on, what they did, what followed, in the writing's terms, with the
-- passages it rests on. A pattern label says that an occasion is an instance of
-- one of the general patterns in `patterns/library.json`, and how it went.
-- Until now both lived in files under data/, read by scripts; the owner could
-- only see them as markdown sheets.
--
-- Three things are recorded that the files left implicit:
--
-- * `fingerprint` binds an occasion to its exact content. Loading the same
--   reading twice changes nothing, and a changed reading is a new occasion
--   rather than a silent edit under verdicts given about the old one.
-- * `labelled_by` names what produced each label. One cheaper model was
--   measured finding 42% of what a stronger one found, so how full a pattern
--   looks depends on who labelled it, and the screen has to be able to say so.
-- * The owner's verdicts, at two levels: whether an occasion is really an
--   instance of the pattern, and whether the pattern rings true at all. A
--   pattern the owner rejects stays visible, marked, rather than disappearing.
--
-- Nothing here is sent to a model. Numbered after 0030 for the same reason:
-- another branch owns 0017-0020.
CREATE TABLE IF NOT EXISTS occasions (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    fingerprint  CHAR(64) NOT NULL,
    actor        VARCHAR(8) NOT NULL CHECK (actor IN ('self', 'other')),
    modality     VARCHAR(16) NOT NULL CHECK (modality IN ('happened', 'planned', 'hypothetical')),
    domain       TEXT,
    situation    TEXT NOT NULL,
    demand       TEXT,
    information  TEXT,
    response     TEXT NOT NULL,
    outcome      TEXT,
    explanation  TEXT,
    occurred_on  DATE,
    -- [{"entryId": "12", "sourceType": "reflection", "entryDate": "2024-05-01", "text": "..."}]
    citations    JSONB NOT NULL DEFAULT '[]'::JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, fingerprint)
);

CREATE TABLE IF NOT EXISTS pattern_labels (
    id             SERIAL PRIMARY KEY,
    occasion_id    INTEGER NOT NULL REFERENCES occasions(id) ON DELETE CASCADE,
    pattern_id     VARCHAR(64) NOT NULL,
    tone           VARCHAR(8) NOT NULL CHECK (tone IN ('better', 'worse', 'mixed')),
    size           VARCHAR(10) CHECK (size IN ('small', 'moderate', 'large')),
    labelled_by    TEXT,
    -- The owner's answer to "is this really an instance of the pattern?".
    -- NULL until they say; 'no' removes it from every count, but keeps the row.
    owner_verdict  VARCHAR(8) CHECK (owner_verdict IN ('yes', 'no', 'unsure')),
    verdict_note   TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (occasion_id, pattern_id)
);

CREATE INDEX IF NOT EXISTS pattern_labels_pattern ON pattern_labels (pattern_id);

CREATE TABLE IF NOT EXISTS pattern_verdicts (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pattern_id  VARCHAR(64) NOT NULL,
    verdict     VARCHAR(12) NOT NULL CHECK (verdict IN ('rings_true', 'does_not', 'unsure')),
    note        TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, pattern_id)
);

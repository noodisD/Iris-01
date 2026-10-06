-- 0048_questionnaire.sql
--
-- The owner's answers to a questionnaire they answer inside IRIS (ADR-0029).
-- The questions themselves are not stored here or in the repository: the text
-- belongs to whoever wrote the questionnaire and stays in a local data file.
--
-- An answer is drafted and kept here, sent nowhere, until the owner adds its
-- section to IRIS. Then it becomes a reflection (source 'questionnaire', a
-- session-format text where the question is context and only the owner's
-- words are evidence). Revising an added answer makes a new version; the old
-- one is kept here as history and its reflection is removed.

ALTER TABLE reflections DROP CONSTRAINT reflections_source_check;
ALTER TABLE reflections
    ADD CONSTRAINT reflections_source_check
        CHECK (source IN ('app', 'cli', 'import', 'voice', 'session', 'questionnaire'));

CREATE TABLE questionnaire_answers (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    questionnaire TEXT NOT NULL,
    question_id   TEXT NOT NULL,
    version       INTEGER NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('draft', 'added', 'superseded', 'skipped')),
    answer        TEXT NOT NULL DEFAULT '',
    -- An answer given in an interview keeps the exchange: [{role, text}], role
    -- 'iris' or 'owner'. The answer itself is only ever the owner's words.
    transcript    JSONB,
    source        TEXT NOT NULL DEFAULT 'form' CHECK (source IN ('form', 'interview')),
    reflection_id INTEGER REFERENCES reflections(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    added_at      TIMESTAMPTZ,
    UNIQUE (user_id, questionnaire, question_id, version)
);
CREATE INDEX questionnaire_answers_question
    ON questionnaire_answers (user_id, questionnaire, question_id, version DESC);

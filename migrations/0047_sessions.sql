-- 0047_sessions.sql
--
-- Therapy sessions (ADR-0028). A session is stored as one reflection whose
-- text names its speakers and keeps every turn apart (content_format
-- 'session', source 'session'), so that only the owner's own turns can become
-- evidence while the therapist's stay context.
--
-- session_passages: the session cut into recall-sized runs of whole turns,
-- each embedded on its own for chat. One vector for an hour of two people
-- talking would match everything a little and nothing well, and the embedding
-- model refuses text that long anyway. Rebuilt whenever the session is
-- processed, so an edit re-cuts it.
--
-- session_imports: a transcript waiting for the owner. Nothing in it has been
-- sent anywhere. It becomes a reflection only once the owner has given the day
-- and time, said which speaker they are, and clicked import. The voices_*
-- columns hold the optional pass that sorts out speakers from the recording,
-- which sends audio to OpenAI and so has its own click.

ALTER TABLE reflections DROP CONSTRAINT reflections_source_check;
ALTER TABLE reflections
    ADD CONSTRAINT reflections_source_check
        CHECK (source IN ('app', 'cli', 'import', 'voice', 'session'));

ALTER TABLE reflections DROP CONSTRAINT reflections_content_format_check;
ALTER TABLE reflections
    ADD CONSTRAINT reflections_content_format_check
    CHECK (content_format IN ('plain', 'markdown', 'session'));

CREATE TABLE session_passages (
    id              SERIAL PRIMARY KEY,
    reflection_id   INTEGER NOT NULL REFERENCES reflections(id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL,
    started_seconds INTEGER NOT NULL,
    text            TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (reflection_id, position)
);
CREATE INDEX session_passages_user ON session_passages (user_id);

CREATE TABLE session_imports (
    id                SERIAL PRIMARY KEY,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status            TEXT NOT NULL DEFAULT 'staged'
                      CHECK (status IN ('staged', 'importing', 'imported', 'discarded')),
    kind              TEXT NOT NULL DEFAULT 'therapy' CHECK (kind IN ('therapy')),
    original_filename TEXT,
    transcript        TEXT NOT NULL,
    transcript_hash   CHAR(64) NOT NULL,
    -- Local wall time, as the owner gave it. A session happened at six in the
    -- evening where the owner was; no zone is guessed for it.
    started_at        TIMESTAMP,
    language          TEXT,
    owner_label       TEXT,
    therapist_label   TEXT,
    -- The transcript as uploaded, kept when the voices pass relabels it, so
    -- the owner can put the transcriber's own labels back.
    original_transcript TEXT,
    audio_path        TEXT,
    audio_seconds     REAL,
    voices_status     TEXT NOT NULL DEFAULT 'none'
                      CHECK (voices_status IN ('none', 'queued', 'running', 'done', 'failed')),
    voices_report     JSONB,
    voices_error      TEXT,
    reflection_id     INTEGER REFERENCES reflections(id) ON DELETE SET NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX session_imports_user ON session_imports (user_id, created_at DESC);

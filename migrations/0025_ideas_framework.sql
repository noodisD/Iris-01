-- Ideas are confirmed propositions, not measured themes.
--
-- A theme counts how often something recurs. An idea is one proposition the
-- owner stated, questioned, or rejected, backed by a verbatim quote, and joined
-- to other propositions only after the owner accepts the connection. Critiques
-- live in their own table so a model's objection is never reread as writing.

CREATE TABLE idea_runs (
    id                SERIAL PRIMARY KEY,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind              TEXT NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at       TIMESTAMPTZ,
    status            TEXT NOT NULL DEFAULT 'running',
    model             TEXT,
    prompt_version    TEXT,
    items_read        INTEGER NOT NULL DEFAULT 0,
    passes_planned    INTEGER NOT NULL DEFAULT 0,
    passes_completed  INTEGER NOT NULL DEFAULT 0,
    proposed          INTEGER NOT NULL DEFAULT 0,
    dropped           JSONB NOT NULL DEFAULT '{}',
    error             TEXT,
    CONSTRAINT idea_runs_kind_check CHECK (kind IN ('discovery', 'links')),
    CONSTRAINT idea_runs_status_check CHECK (status IN ('running', 'complete', 'partial', 'failed'))
);

CREATE INDEX idea_runs_user_started_idx
    ON idea_runs (user_id, started_at DESC, id DESC);

CREATE TABLE ideas (
    id             SERIAL PRIMARY KEY,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    statement      TEXT NOT NULL,
    statement_key  CHAR(64) NOT NULL,
    domain         TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'candidate',
    position       TEXT NOT NULL DEFAULT 'exploring',
    run_id         INTEGER REFERENCES idea_runs(id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed_at   TIMESTAMPTZ,
    CONSTRAINT ideas_statement_check
        CHECK (length(btrim(statement)) > 0 AND char_length(statement) <= 600),
    CONSTRAINT ideas_domain_check
        CHECK (domain IN ('philosophy', 'economics', 'politics', 'ethics', 'other')),
    CONSTRAINT ideas_status_check
        CHECK (status IN ('candidate', 'active', 'rejected')),
    CONSTRAINT ideas_position_check
        CHECK (position IN ('exploring', 'endorsed', 'opposed')),
    CONSTRAINT ideas_user_statement_key_unique UNIQUE (user_id, statement_key),
    CONSTRAINT ideas_user_id_unique UNIQUE (user_id, id)
);

CREATE INDEX ideas_user_status_idx ON ideas (user_id, status);

CREATE TABLE idea_citations (
    id             SERIAL PRIMARY KEY,
    idea_id        INTEGER NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
    reflection_id  INTEGER NOT NULL REFERENCES reflections(id) ON DELETE CASCADE,
    quote          TEXT NOT NULL,
    quote_hash     CHAR(64) NOT NULL,
    source_hash    CHAR(64) NOT NULL,
    stance         TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'candidate',
    run_id         INTEGER REFERENCES idea_runs(id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT idea_citations_quote_check CHECK (length(btrim(quote)) > 0),
    CONSTRAINT idea_citations_stance_check
        CHECK (stance IN ('endorsed', 'questioned', 'opposed')),
    CONSTRAINT idea_citations_status_check
        CHECK (status IN ('candidate', 'accepted', 'rejected')),
    CONSTRAINT idea_citations_unique UNIQUE (idea_id, reflection_id, quote_hash)
);

CREATE INDEX idea_citations_reflection_idx ON idea_citations (reflection_id);
CREATE INDEX idea_citations_idea_status_idx ON idea_citations (idea_id, status);

CREATE TABLE idea_links (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    from_idea_id  INTEGER NOT NULL,
    to_idea_id    INTEGER NOT NULL,
    kind          TEXT NOT NULL,
    rationale     TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'candidate',
    run_id        INTEGER REFERENCES idea_runs(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed_at  TIMESTAMPTZ,
    CONSTRAINT idea_links_kind_check
        CHECK (kind IN ('supports', 'contradicts', 'refines', 'depends_on')),
    CONSTRAINT idea_links_status_check
        CHECK (status IN ('candidate', 'accepted', 'rejected')),
    CONSTRAINT idea_links_rationale_check
        CHECK (length(btrim(rationale)) > 0 AND char_length(rationale) <= 1200),
    CONSTRAINT idea_links_no_self CHECK (from_idea_id <> to_idea_id),
    CONSTRAINT idea_links_contradicts_order
        CHECK (kind <> 'contradicts' OR from_idea_id < to_idea_id),
    CONSTRAINT idea_links_from_fk
        FOREIGN KEY (user_id, from_idea_id) REFERENCES ideas (user_id, id) ON DELETE CASCADE,
    CONSTRAINT idea_links_to_fk
        FOREIGN KEY (user_id, to_idea_id) REFERENCES ideas (user_id, id) ON DELETE CASCADE,
    CONSTRAINT idea_links_unique UNIQUE (user_id, from_idea_id, to_idea_id, kind)
);

CREATE INDEX idea_links_user_status_idx ON idea_links (user_id, status);
CREATE INDEX idea_links_to_idea_idx ON idea_links (to_idea_id);

CREATE TABLE idea_critiques (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    idea_id         INTEGER NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    model           TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    input_hash      CHAR(64) NOT NULL,
    basis           JSONB NOT NULL,
    content         JSONB NOT NULL,
    CONSTRAINT idea_critiques_idea_fk
        FOREIGN KEY (user_id, idea_id) REFERENCES ideas (user_id, id) ON DELETE CASCADE
);

CREATE INDEX idea_critiques_idea_created_idx
    ON idea_critiques (idea_id, created_at DESC, id DESC);

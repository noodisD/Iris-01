-- 0008_constructs.sql
--
-- Themes that were noticed by reading, not found by clustering.
--
-- Every theme so far is a cluster of embeddings with a label generated after
-- the fact. That can say how often an unnamed group of entries recurred, and
-- nothing else. On the live archive it split one subject into five separate
-- near-identical themes of 2-7 occurrences each, so no single one carried enough
-- evidence to say anything, and not one of them named a behaviour.
--
-- A construct is the other direction: something a reader noticed in the owner's
-- own words, quoted verbatim, that the owner then confirmed. Because it is
-- stored as a theme, every existing engine measures it with no new arithmetic —
-- trajectory, resolution, tension, leverage and decision impact all iterate
-- themes generically.
--
-- `status` is the gate. A candidate is not measured by anything until the owner
-- confirms it; that is what keeps a model's fluent guess from becoming a
-- counted pattern. Existing rows are 'clustered' and 'active', so nothing about
-- the current 18 themes changes.
--
-- `definition` holds the claim in the reader's words and is deliberately NOT
-- embedded (ADR-0014). The centroid is built from `theme_prototypes` alone —
-- the owner's sentences — so a construct is anchored in what was written rather
-- than in how a model described it.

ALTER TABLE themes ADD COLUMN IF NOT EXISTS origin VARCHAR(16) NOT NULL DEFAULT 'clustered';
ALTER TABLE themes ADD COLUMN IF NOT EXISTS definition TEXT;
ALTER TABLE themes ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'active';
ALTER TABLE themes ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS theme_prototypes (
    id          SERIAL PRIMARY KEY,
    theme_id    INTEGER NOT NULL REFERENCES themes(id) ON DELETE CASCADE,
    source_type VARCHAR(32) NOT NULL,
    source_id   INTEGER,
    quote       TEXT NOT NULL,
    vector      vector(1536),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- The engines read themes by user and status on every analysis pass.
CREATE INDEX IF NOT EXISTS idx_themes_user_status ON themes(user_id, status);
CREATE INDEX IF NOT EXISTS idx_theme_prototypes_theme ON theme_prototypes(theme_id);

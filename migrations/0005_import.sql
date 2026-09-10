-- 0005_import.sql
--
-- Bringing existing writing into IRIS: journals exported from other tools, and
-- voice recordings. Imported entries are reflections like any other (ADR-0010);
-- what they need is provenance, a way to recognise a re-import, and somewhere to
-- sit while the owner checks the dates before anything becomes evidence.

-- --------------------------------------------------------------------------
-- Provenance and de-duplication on reflections
-- --------------------------------------------------------------------------

-- Where the entry came from. Existing rows are 'app'.
ALTER TABLE reflections
    ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'app';

ALTER TABLE reflections
    ADD CONSTRAINT reflections_source_check
        CHECK (source IN ('app', 'cli', 'import', 'voice'));

-- sha256 of the whitespace-normalised content, so a CRLF export and an LF export
-- of the same entry are recognised as one entry.
--
-- Deliberately only written by the importer. It could be computed for every new
-- reflection, but that would make the unique index below reject an entry typed
-- twice in one day through the app or the CLI -- a 500 from a feature those
-- paths never used. Nothing there needs de-duplication; re-importing a file
-- does. Existing and app-written rows keep NULL and stay outside the constraint.
ALTER TABLE reflections
    ADD COLUMN IF NOT EXISTS content_hash CHAR(64);

-- Relative to the audio root, never absolute, so the data directory can move.
ALTER TABLE reflections
    ADD COLUMN IF NOT EXISTS audio_path TEXT;

-- The key is (user, day, text): the same words on a different day are a second
-- entry someone genuinely wrote, while the same words on the same day are what
-- re-importing the same export produces. Partial, so the NULL-hash rows above do
-- not collide with each other.
CREATE UNIQUE INDEX IF NOT EXISTS uq_reflections_user_day_hash
    ON reflections (user_id, reflection_date, content_hash)
    WHERE content_hash IS NOT NULL;

-- --------------------------------------------------------------------------
-- Staging
-- --------------------------------------------------------------------------
--
-- Parsed entries wait here until the owner has seen what was detected. Staging
-- in the database rather than round-tripping the parse through the browser is
-- what makes the review survive a reload, gives per-entry errors somewhere to
-- live, and lets a commit resume. It also means an entry is never created and
-- then retracted: once a reflection has been embedded and matched to a theme,
-- undoing it is real work, so the cheapest correction is the one made before it
-- exists.

CREATE TABLE IF NOT EXISTS import_batches (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind VARCHAR(20) NOT NULL,              -- 'text' | 'audio'
    adapter VARCHAR(50),                    -- which format was used to read it
    detected JSONB,                         -- [{adapter, label, score}, ...]
    original_filename TEXT,
    stored_path TEXT,                       -- upload, kept until the batch closes
    status VARCHAR(20) NOT NULL DEFAULT 'uploaded',
    error TEXT,
    entry_count INTEGER NOT NULL DEFAULT 0,
    committed_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT import_batches_kind_check
        CHECK (kind IN ('text', 'audio')),
    CONSTRAINT import_batches_status_check
        CHECK (status IN ('uploaded', 'parsing', 'needs_review',
                          'committing', 'committed', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_import_batches_user
    ON import_batches (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS import_items (
    id SERIAL PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_name TEXT,                       -- the path inside the export
    title TEXT,
    content TEXT NOT NULL DEFAULT '',       -- empty for audio until transcribed
    content_hash CHAR(64),
    audio_path TEXT,
    -- NULL means the date could not be determined. An item in that state is
    -- shown for correction and refused at commit: reflection_date becomes
    -- occurred_at for every analytical window, so a guessed date is not a small
    -- inaccuracy, it is a wrong answer everywhere, silently.
    entry_date DATE,
    date_source VARCHAR(20),                -- 'filename' | 'frontmatter' | ...
    date_confidence VARCHAR(10) NOT NULL DEFAULT 'unknown',
    tags JSONB,
    warnings JSONB,
    status VARCHAR(20) NOT NULL DEFAULT 'staged',
    -- Not a foreign key on purpose: this row is the record of what the import
    -- did, and it should outlive a reflection the owner later deletes.
    reflection_id INTEGER,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT import_items_status_check
        CHECK (status IN ('staged', 'excluded', 'duplicate', 'imported', 'failed')),
    CONSTRAINT import_items_date_confidence_check
        CHECK (date_confidence IN ('certain', 'probable', 'unknown'))
);

CREATE INDEX IF NOT EXISTS idx_import_items_batch
    ON import_items (batch_id, id);

CREATE INDEX IF NOT EXISTS idx_import_items_hash
    ON import_items (user_id, content_hash);

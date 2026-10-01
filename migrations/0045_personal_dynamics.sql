-- Replace library-first derived discovery with owner-scoped, versioned personal dynamics.
-- The migration runner executes this file and its ledger entry in one transaction.
-- Preserve opinions before dropping any of the old derived tables. In particular,
-- owner_tone and note-only rows are opinions even when verdict is NULL.
CREATE TABLE discovery_legacy_feedback (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('occasion', 'pattern', 'ordered_pair')),
    legacy_key TEXT NOT NULL,
    source_ids INTEGER[] NOT NULL DEFAULT '{}',
    payload JSONB NOT NULL,
    archived_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, kind, legacy_key)
);

-- Keep the old label's identity, the linked source IDs and only the saved
-- opinion/tone fields; never preserve copied excerpts or generated label prose.
INSERT INTO discovery_legacy_feedback (user_id, kind, legacy_key, source_ids, payload)
SELECT o.user_id, 'occasion', l.id::text,
       ARRAY(SELECT DISTINCT os.reflection_id
               FROM occasion_sources os
               JOIN reflections r ON r.id = os.reflection_id AND r.user_id = o.user_id
              WHERE os.occasion_id = o.id
              ORDER BY os.reflection_id),
       jsonb_build_object('occasionId', o.id, 'fingerprint', o.fingerprint,
                          'patternId', l.pattern_id, 'tone', l.tone,
                          'ownerTone', l.owner_tone, 'ownerVerdict', l.owner_verdict,
                          'verdictNote', l.verdict_note, 'createdAt', l.created_at)
  FROM pattern_labels l
  JOIN occasions o ON o.id = l.occasion_id
 WHERE l.owner_verdict IS NOT NULL OR l.verdict_note IS NOT NULL
    OR l.owner_tone IS NOT NULL OR l.tone IS NOT NULL;

INSERT INTO discovery_legacy_feedback (user_id, kind, legacy_key, source_ids, payload)
SELECT v.user_id, 'pattern', v.pattern_id,
       ARRAY(SELECT DISTINCT os.reflection_id
               FROM pattern_labels l
               JOIN occasions o ON o.id = l.occasion_id AND o.user_id = v.user_id
               JOIN occasion_sources os ON os.occasion_id = o.id
               JOIN reflections r ON r.id = os.reflection_id AND r.user_id = v.user_id
              WHERE l.pattern_id = v.pattern_id
              ORDER BY os.reflection_id),
       jsonb_build_object('patternId', v.pattern_id, 'verdict', v.verdict,
                          'note', v.note, 'updatedAt', v.updated_at)
  FROM pattern_verdicts v
 WHERE v.verdict IS NOT NULL OR v.note IS NOT NULL;

-- JSON-array keys avoid collisions when pattern IDs contain punctuation. The
-- ordered pair is intentionally not canonicalised: the former PK was ordered.
INSERT INTO discovery_legacy_feedback (user_id, kind, legacy_key, source_ids, payload)
SELECT v.user_id, 'ordered_pair',
       jsonb_build_array(v.pattern_id, v.other_pattern_id)::text,
       ARRAY(SELECT DISTINCT os.reflection_id
               FROM pattern_labels l
               JOIN occasions o ON o.id = l.occasion_id AND o.user_id = v.user_id
               JOIN occasion_sources os ON os.occasion_id = o.id
               JOIN reflections r ON r.id = os.reflection_id AND r.user_id = v.user_id
              WHERE l.pattern_id IN (v.pattern_id, v.other_pattern_id)
              ORDER BY os.reflection_id),
       jsonb_build_object('patternId', v.pattern_id, 'otherPatternId', v.other_pattern_id,
                          'verdict', v.verdict, 'note', v.note, 'updatedAt', v.updated_at)
  FROM difference_verdicts v
 WHERE v.verdict IS NOT NULL OR v.note IS NOT NULL;

DROP TABLE difference_verdicts;
DROP TABLE pattern_verdicts;
DROP TABLE pattern_labels;
DROP TABLE occasion_sources;
DROP TABLE occasions;
DROP TABLE discovery_reads;

CREATE TABLE discovery_reads (
    reflection_id INTEGER PRIMARY KEY REFERENCES reflections(id) ON DELETE CASCADE,
    source_revision BIGINT NOT NULL,
    extraction_version INTEGER NOT NULL,
    reader_version CHAR(64) NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    omitted_accounts INTEGER NOT NULL DEFAULT 0 CHECK (omitted_accounts >= 0),
    omitted_fields INTEGER NOT NULL DEFAULT 0 CHECK (omitted_fields >= 0)
);

-- A composite FK enforces the reflection owner as well as its existence.
ALTER TABLE reflections ADD CONSTRAINT reflections_user_id_id_key UNIQUE (user_id, id);
CREATE TABLE discovery_accounts (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    id CHAR(64) NOT NULL,
    reflection_id INTEGER NOT NULL,
    source_revision BIGINT NOT NULL,
    reader_version CHAR(64) NOT NULL,
    data JSONB,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (user_id, id),
    FOREIGN KEY (user_id, reflection_id) REFERENCES reflections(user_id, id) ON DELETE CASCADE,
    CHECK (NOT is_current OR data IS NOT NULL)
);
CREATE INDEX discovery_accounts_user_current ON discovery_accounts (user_id, is_current);
CREATE INDEX discovery_accounts_reflection ON discovery_accounts (reflection_id);

CREATE TABLE discovery_state (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    source_generation BIGINT NOT NULL DEFAULT 1,
    review_generation BIGINT NOT NULL DEFAULT 0,
    stage TEXT NOT NULL DEFAULT 'reading'
        CHECK (stage IN ('reading', 'discovering', 'checking', 'interpreting', 'ready', 'failed')),
    error_kind TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE discovery_drafts (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    source_generation BIGINT NOT NULL,
    manifest_hash CHAR(64) NOT NULL,
    source_manifest JSONB NOT NULL,
    discovery_version CHAR(64) NOT NULL,
    model TEXT NOT NULL,
    payload JSONB NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE discovery_views (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    range TEXT NOT NULL CHECK (range IN ('all', '30d', '90d')),
    source_generation BIGINT NOT NULL,
    review_generation BIGINT NOT NULL,
    manifest_hash CHAR(64) NOT NULL,
    as_of DATE NOT NULL,
    interpretation_version CHAR(64) NOT NULL,
    library_hash CHAR(64) NOT NULL,
    model TEXT NOT NULL,
    payload JSONB NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (user_id, range)
);

CREATE TABLE discovery_feedback (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    object_kind TEXT NOT NULL CHECK (object_kind IN ('dynamic', 'insight')),
    object_id TEXT NOT NULL,
    range TEXT NOT NULL CHECK (range IN ('all', '30d', '90d')),
    judged_hash CHAR(64) NOT NULL,
    verdict TEXT CHECK (verdict IN ('rings_true', 'does_not', 'unsure')),
    note TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, object_kind, object_id, range)
);

CREATE TABLE discovery_membership_feedback (
    user_id INTEGER NOT NULL,
    dynamic_id TEXT NOT NULL,
    account_id CHAR(64) NOT NULL,
    verdict TEXT CHECK (verdict IN ('yes', 'no', 'unsure')),
    note TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, dynamic_id, account_id),
    FOREIGN KEY (user_id, account_id) REFERENCES discovery_accounts(user_id, id) ON DELETE CASCADE
);

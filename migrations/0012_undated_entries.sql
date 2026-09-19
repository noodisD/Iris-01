-- 0012_undated_entries.sql
--
-- Writing that carries no date, represented end to end instead of refused at
-- the door.
--
-- ADR-0013 says a date is read or it is absent, never invented. Until now the
-- second half was unreachable: reflection_date and occurred_at were both NOT
-- NULL, so "absent" had nowhere to live and the import refused to commit an
-- undated entry at all. Forty-three voice transcripts — 318,000 characters of
-- the owner's thinking — sat staged and unreadable for want of a column that
-- could say "unknown".
--
-- Nothing here invents a date. It makes the absence storable, so undated
-- writing can be recalled, read and counted, while every measurement that
-- needs a point in time keeps refusing to guess one.
--
-- The counters stay apart. `occurrence_count` continues to mean occurrences
-- that can be placed in time, because that is what every window engine gates
-- on; occurrences without a date are counted beside it and never summed into
-- it unlabelled (ADR-0009, and the same rule mention/behaviour follows).

-- --------------------------------------------------------------------------
-- Entries
-- --------------------------------------------------------------------------

ALTER TABLE reflections ALTER COLUMN reflection_date DROP NOT NULL;

-- Where the entry sits in an ordering that is known even when the dates are
-- not: a transcript file numbers its recordings, so the sequence is read from
-- the source exactly as a date would be. It orders undated entries among
-- themselves and never stands in for a date — nothing derives a day from it.
ALTER TABLE reflections ADD COLUMN IF NOT EXISTS entry_sequence INTEGER;

-- The de-duplication key is (user, day, text). Two NULLs are never equal in a
-- unique index, so undated entries would stop colliding and re-importing the
-- same export would silently double them. -infinity is a real DATE value that
-- compares equal to itself, which restores the guard for undated rows without
-- touching dated ones.
DROP INDEX IF EXISTS uq_reflections_user_day_hash;
CREATE UNIQUE INDEX IF NOT EXISTS uq_reflections_user_day_hash
    ON reflections (user_id, COALESCE(reflection_date, '-infinity'::date), content_hash)
    WHERE content_hash IS NOT NULL;

-- --------------------------------------------------------------------------
-- Occurrences
-- --------------------------------------------------------------------------

-- An occurrence in undated writing is a real occurrence; what it is not is a
-- point in a window. Readers ask for dated occurrences by default, so the six
-- window engines see exactly what they saw before this migration.
ALTER TABLE theme_occurrences ALTER COLUMN occurred_at DROP NOT NULL;

ALTER TABLE themes
    ADD COLUMN IF NOT EXISTS undated_occurrence_count INTEGER NOT NULL DEFAULT 0;

-- --------------------------------------------------------------------------
-- Import
-- --------------------------------------------------------------------------

-- "No date could be read" and "the owner has looked and says it is unknown"
-- are different states with different remedies, and only the second may be
-- committed. Default false, so an export whose dates failed to parse is still
-- held back for review exactly as before.
ALTER TABLE import_items
    ADD COLUMN IF NOT EXISTS date_unknown_accepted BOOLEAN NOT NULL DEFAULT FALSE;

-- 0015_retire_journal_entries.sql
--
-- A journal entry is a reflection (ADR-0010). The product stopped writing
-- `journal_entries` long ago and scripts/backfill_journal_entries.py moved what
-- was there into `reflections`; on the owner's database the table, and every
-- embedding, occurrence and queued job that could point at it, is empty. What
-- kept it alive was the test suite seeding it and seven queries unioning it in
-- as if it might hold evidence.
--
-- Dropping a table is not undone by a later migration, so this refuses to run
-- unless there is nothing to lose: no rows, and nothing referring to a row.
-- A database that still has legacy entries stops here with the reason, and
-- the backfill script is the way forward.
DO $$
DECLARE
    remaining bigint;
BEGIN
    IF to_regclass('journal_entries') IS NULL THEN
        RETURN;
    END IF;
    SELECT (SELECT count(*) FROM journal_entries)
         + (SELECT count(*) FROM embeddings WHERE source_type = 'journal_entry')
         + (SELECT count(*) FROM theme_occurrences WHERE source_type = 'journal_entry')
         + (SELECT count(*) FROM processing_queue WHERE source_type = 'journal_entry')
      INTO remaining;
    IF remaining > 0 THEN
        RAISE EXCEPTION 'journal_entries still holds or is referenced by % row(s); '
                        'run scripts/backfill_journal_entries.py first', remaining;
    END IF;
END $$;

DROP TABLE IF EXISTS journal_entries;

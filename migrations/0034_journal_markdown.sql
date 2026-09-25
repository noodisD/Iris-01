-- 0034_journal_markdown.sql
--
-- A journal entry may be markdown. Imported prose that contains * or _ stays
-- plain, so those characters are never read as formatting and never stripped.
--
-- A daily check-in is stored in the existing metrics JSONB. Energy stays in
-- energy_level, so the Decisions and Review screens keep reading that column.
-- The tag-inferred mood column is left alone.

ALTER TABLE reflections
    ADD COLUMN content_format VARCHAR(16) NOT NULL DEFAULT 'plain';

ALTER TABLE reflections
    ADD CONSTRAINT reflections_content_format_check
    CHECK (content_format IN ('plain', 'markdown'));

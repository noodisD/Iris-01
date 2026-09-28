-- 0041_idea_notes.sql
--
-- An idea's own page: the owner's notes about it, in Markdown, where
-- [[another idea's statement]] links to that idea. Notes are the owner's
-- writing about an idea, not evidence for it, so they never count as a quote.
ALTER TABLE ideas ADD COLUMN notes TEXT NOT NULL DEFAULT ''
    CHECK (char_length(notes) <= 20000);
ALTER TABLE ideas ADD COLUMN notes_updated_at TIMESTAMPTZ;

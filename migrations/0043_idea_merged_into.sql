-- 0043_idea_merged_into.sql
--
-- A proposal the owner recognised as an idea they already hold. Its quotes
-- move to that idea and the proposal is set aside, but discovery must not
-- treat the wording as dismissed: a later passage in the same words belongs to
-- the idea it was folded into, as new quotes for it.
ALTER TABLE ideas ADD COLUMN merged_into_id INTEGER REFERENCES ideas(id) ON DELETE SET NULL;
ALTER TABLE ideas ADD CONSTRAINT ideas_merged_into_is_other CHECK (merged_into_id IS NULL OR merged_into_id <> id);

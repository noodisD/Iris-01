-- 0006_import_file_dates.sql
--
-- When a file in an upload was last saved, where the upload carried that time:
-- a zip records one for every member, and a browser knows it for a single file.
--
-- Kept as evidence, not as a date. ADR-0013 rules out falling back to a file's
-- modification time and that still holds: nothing reads this column to date an
-- entry on its own. The owner can choose to use it for an entry that has no
-- other date, and the entry is then marked probable, never certain.
--
-- A column of its own rather than a guess written into entry_date, so the
-- difference between "the export said this day" and "a file was saved on this
-- day" survives into review.

ALTER TABLE import_items ADD COLUMN IF NOT EXISTS file_modified_at TIMESTAMPTZ;

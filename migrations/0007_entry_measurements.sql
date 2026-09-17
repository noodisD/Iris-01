-- 0007_entry_measurements.sql
--
-- What the originals recorded, and whether an entry is evidence.
--
-- The earlier-IRIS export carries typed wellbeing values on every entry — mood
-- and energy on all 24, and sleep hours, sleep quality, exercise, nutrition,
-- anxiety or stress on most — and the importer read only the prose beside them.
-- All 138 imported reflections therefore have no energy, no clarity, and the
-- mood "okay" that _infer_mood returns for an entry with no tags: a default
-- presented as something the owner recorded. `metrics` keeps the source's own
-- values with their own scales; unknown stays null.
--
-- `date_source` and `date_confidence` follow the entry out of staging. 35 of
-- the 138 dates are probable, and that uncertainty stopped at the import table
-- while the engines treated every date as equally good.
--
-- `evidence_eligible` separates memory from evidence. Copied setup text and
-- six-character placeholders were counted as occurrences of a pattern, which
-- is how repetition gets manufactured; they stay searchable and quotable, and
-- stop being proof that something recurred.

ALTER TABLE reflections ADD COLUMN IF NOT EXISTS metrics JSONB;
ALTER TABLE reflections ADD COLUMN IF NOT EXISTS date_source VARCHAR(20);
ALTER TABLE reflections ADD COLUMN IF NOT EXISTS date_confidence VARCHAR(10);
ALTER TABLE reflections ADD COLUMN IF NOT EXISTS evidence_eligible BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE import_items ADD COLUMN IF NOT EXISTS metrics JSONB;

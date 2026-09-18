-- 0011_undated_spans.sql
--
-- A construct built from undated writing has no span, and should say so.
--
-- Voice transcripts carry no date. That is deliberate: a date is read or it is
-- absent, never invented (ADR-0013), and the 43 staged recordings have none.
-- But `promote()` needed *something* for `first_seen_at` and `last_seen_at`,
-- which are NOT NULL, so it used the moment of discovery. Four candidates
-- therefore record a span of the day they were found, which reads as though the
-- owner wrote those recordings that afternoon.
--
-- Two ways to fix it. Making the timestamps nullable is the truthful shape, and
-- it changes three engines plus everything that sorts or formats those dates.
-- This is the other: an additive flag that only the review surface reads. The
-- timestamps keep a value the columns require, and the flag says plainly that
-- the value means nothing — so no consumer has to learn about null, and no
-- screen can quietly present a placeholder as a date.
--
-- The narrower fix, chosen because the broader one would have touched
-- narrative, prioritisation and decision impact to solve a display problem.

ALTER TABLE themes ADD COLUMN IF NOT EXISTS span_is_undated BOOLEAN NOT NULL DEFAULT FALSE;

-- Everything that exists was built from dated reflections, or is a cluster whose
-- occurrences all carry days. None of them are undated.
UPDATE themes SET span_is_undated = FALSE WHERE span_is_undated IS NULL;

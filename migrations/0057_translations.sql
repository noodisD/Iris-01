-- 0057_translations.sql
--
-- A record written in another language keeps its original words and gains one
-- English version, which the reader, chat and the journal use (ADR-0036).
-- translation_hash is the sha256 of the content it was made from: a
-- translation whose hash no longer matches is of words that are gone, and is
-- not used.

ALTER TABLE reflections ADD COLUMN translation TEXT;
ALTER TABLE reflections ADD COLUMN translation_hash TEXT;

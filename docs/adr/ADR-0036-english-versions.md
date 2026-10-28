# ADR-0036: A record in another language is read in English, its original kept

## Status
Accepted — 2026-10-28

## Context
The owner reads, writes and asks in English, and almost all of the archive is
English. Therapy sessions are recorded in Polish, along with a stray entry
and a questionnaire answer. They were kept and read in Polish: pattern
accounts quoted Polish, chat recalled Polish passages through an English
gloss vector (ADR-0035), and the journal showed Polish. The owner wants the
records to read as one archive, in English.

IRIS stands on quotes found word for word in what the owner said. A
translation is a model's words, so replacing the original was ruled out: a
mistranslation could never be caught, and the record would no longer be the
owner's.

## Decision
- **One stored English version, the original kept.** `reflections.translation`
  holds it and `translation_hash` the sha256 of the content it was made from
  (migration 0057). A translation whose hash no longer matches is not used,
  and an edit clears it in the same commit.
- **Made by the worker model, checked for wholeness.** `agent/translation.py`
  translates a session turn by turn, twenty at a time, and keeps the session
  format with the same speakers and times, so `sessions.owner_turn` answers
  "whose words?" the same way. A reply missing a turn, or with a turn far
  longer or shorter than its original, is asked once more and then not kept;
  the record is read in its own words as before. The local term list
  (ADR-0035) gives recurring terms one rendering.
- **Everything that reads uses the English.** The reader reads it and its
  quotes are checked against it (`discovery._source_rows`), so pattern
  accounts quote the English of the owner's own turns. Recall passages and
  vectors are cut from it, and chat's recent entries and recalled entries
  show it (`database.READ_TEXT`). The doctor's quote check uses it too.
- **The journal shows the English first.** The original is one tap away
  ("Show the Polish"), labelled as the original.
- **New records are translated as they are processed.** Records already in
  IRIS are caught up with `scripts/translate_records.py`, which shows the
  cost first and then queues them to be indexed and read again.
- **Ideas keep the originals.** Idea citations are checked against the
  stored words by hash in many places; they stay on the originals for now.

## Consequences
- A quote from a translated record is a translation of what the owner said.
  It is still found word for word in the English of an owner's turn, and that
  turn's original is one tap away in the journal.
- Translating costs one worker call per twenty turns: a few cents for an
  hour-long session, shown before the catch-up runs and added to the import.
- A record whose translation failed is read in its own language, as before,
  and the catch-up script lists it.

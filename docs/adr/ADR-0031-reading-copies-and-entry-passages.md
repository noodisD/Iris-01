# ADR-0031: Dictated entries are read from a reading copy; long entries are recalled by passage

## Status
Accepted — 2026-10-12

## Context
An audit of the archive found two weaknesses in how entries reach the models.

Dictated entries, which arrive as one long breath with no punctuation, yielded
about half as many events and self-reports per thousand words as written ones.
Reading copies (`readable.py`: punctuation put in, not one word changed) had
been made for them, but only in an offline cache that the experiments used; the
live reader never saw them.

Chat recalls an entry by one embedding of the whole entry. A fifth of the
journal is over 400 words and twenty entries are over 1,500, so their vectors
are the average of many subjects. What chat was then shown was a 300-character
window picked by shared words, which misses an inflected form, and on an entry
with no sentence breaks falls back to the opening.

## Decision
- **Reading copies are stored and used live.** `reflections.reading_copy`
  (migration 0050) holds the copy. It is made by the worker model when an entry
  is processed or read and needs one (`needs_tidying`). It is used only while
  `same_words` holds against the entry, and any edit clears it. The discovery
  reader reads the copy, and its quotes are located back in the entry's own
  text, as `readable.py` and `episodes.py` already do.
- **Long entries are cut into passages.** An entry over 250 words is cut into
  runs of whole sentences of about 150 words, at most 250 (`entry_passages.py`).
  A dictated entry is cut from its reading copy. Each run is embedded as an
  `entry_passage`, rebuilt whenever the entry is processed. Search no longer
  uses the whole-entry vector of an entry that has passages. Chat shows the
  passage that matched, whole, marked as part of a longer entry, and
  questionnaire suggestions can quote from it.
- **The archive catches up by a script.** `scripts/backfill_reading.py` stores
  the cached copies, makes missing ones, and cuts the passages. With
  `--reread` it re-reads the entries that have copies, which replaces their
  accounts and sets off one pattern update. It prints the cost first and is
  run by the owner's choice.

## Consequences
- More of what the owner dictated becomes accounts, and chat finds and shows
  the part of a long entry that answers the question.
- Short entries are recalled exactly as before. Whole-entry vectors stay in
  place for the theme engine, which is unchanged.
- A reading copy that fails the word check is simply not made. That entry is
  read and cut from its own text, as before.

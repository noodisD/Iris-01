# ADR-0013: Imported and spoken entries are reflections, dated when they happened

## Status
Accepted — 2026-09-10

## Context
Every engine in IRIS needs volume it did not have. A theme needs five
occurrences to exist at all; trajectory compares fourteen days against sixty;
resolution needs twenty-one. Meanwhile the only way in was `POST /api/journal`:
one entry, no date field, dated today. Years of existing writing in other tools,
and a backlog of voice recordings, could not get in at all.

## Decision

**An imported entry is a reflection.** Not a new source type, not a second
store — ADR-0010 already settled that a journal entry *is* a reflection, and an
entry written in Notion is not a different kind of thing from one typed here.
Committing goes through `ReflectionService.create_reflection`, the same seam the
app and the CLI use, so an imported entry is enqueued, embedded and offered to
the engines exactly like anything else. Importing does not become a second way
for data to enter the system.

**A date is read, or it is absent.** There is no fallback to today and none to a
file's modification time. `reflection_date` becomes `occurred_at` for every
analytical window, so a guessed date is not a small inaccuracy in one row: it
moves an entry into or out of the recent window, the baseline, and the silence a
dissipation is measured against — and nothing downstream can tell a guess from a
known date. An entry whose date cannot be determined is staged with none, shown
for correction, and refused at commit. Genuinely ambiguous input (`03/04/2024`)
is marked *probable* with a note naming both readings rather than quietly picked.

**Nothing becomes a reflection until it has been reviewed.** The source format is
not known in advance, dates come from filenames and property blocks written by
other tools, and an export contains plenty that is not a journal entry — a Notion
export carries recipes and meeting notes as readily as journals. Each of those is
cheap to correct before a reflection exists and expensive after: once an entry is
embedded and matched to a theme, undoing it is real work. So parsed entries are
staged in `import_items` and the owner sees what was detected first.

**Format detection is a guess, and says so.** A registry of adapters each score
how well they recognise a bundle; the best wins, the result is shown, and it can
be overruled. An export from a tool nobody anticipated falls through to
"every file is an entry, check the dates" rather than to a failure.

**`transcription` and `import_parse` are queue job kinds, not evidence source
types.** ADR-0003 asks anything new to say which side of the evidence line it
falls on. The answer here is neither: audio is not evidence, and a transcript
becomes evidence only once it is committed as a reflection. They must never
appear in `EVIDENCE_WEIGHTS` or `get_unassigned_embeddings`, which is why they
are dispatched in `work_queue` rather than taught to `run_processing_pipeline`,
whose table map is a map of evidence sources.

**The recording is kept.** Transcription is lossy and cannot be un-made: a
garbled sentence is unrecoverable if the original is gone, and a better model
next year cannot re-read a file that no longer exists. Audio is stored
content-addressed under `data/audio/`, conversions happen on throwaway copies,
and the transcript is treated as derived.

**`content_hash` is written by the importer only.** It could be computed for
every reflection, but then the de-duplication index would reject an entry typed
twice in one day through the app — a 500 from a feature those paths never touch.
Nothing there needs de-duplication; re-importing a file does.

## Consequences
Existing writing can come in dated when it was written, and the analytical layer
sees it as history rather than as a burst of activity today.

An import of any size is eventually consistent, like every other write
(ADR-0011): entries appear immediately, and themes catch up as the queue drains.
A large import can also reorganise the themes that already exist, because
clustering sees a different set once hundreds of entries arrive at once. The
screen says so rather than implying otherwise.

The review step is not optional and cannot be skipped by an API caller either —
the commit endpoint returns 409 while any included entry lacks a date. Anything
that wanted to import without review would have to reopen this ADR.

Undo is supported because the dates are the point: if an export is read with the
wrong format and hundreds of entries land on the wrong days, living with it is
not an acceptable answer. Deleting a batch takes its reflections, their
embeddings and their occurrences, then refreshes the affected themes.

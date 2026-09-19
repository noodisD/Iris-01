# ADR-0013: Imported and spoken entries are reflections, dated when they happened

## Status
Accepted — 2026-09-10 · Amended 2026-09-11, 2026-09-19

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

**A file's saved time is offered, never applied.** *(Amended 2026-09-11, at the
owner's request, for a vault of notes with no date anywhere in them.)* Where an
upload records when each file was last saved — a zip does for every member, a
browser does for a single file — that time is kept beside the entry
(`import_items.file_modified_at`) and offered in review. Choosing it dates the
entry *probable*, shown amber, and only an entry with no other date; it never
replaces a date the writing gave. It is not offered where it would be worse than
nothing: a time the server made itself (its copy of an upload is dated when it
arrived — "dated today", one step removed); a day several files share, which is
when a copy or an export was made, the trap the Elara export set with its `date`
field; and a file holding several entries, which has one time between them.

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

**`transcription` is a queue job kind, not an evidence source type.** ADR-0003
asks anything new to say which side of the evidence line it falls on. The answer
here is neither: audio is not evidence, and a transcript becomes evidence only
once it is committed as a reflection. It must never appear in `EVIDENCE_WEIGHTS`
or `get_unassigned_embeddings`, which is why it is dispatched in `work_queue`
rather than taught to `run_processing_pipeline`, whose table map is a map of
evidence sources.

Parsing an upload is *not* queued. An earlier version of this ADR said it was,
and named an `import_parse` job kind that was never built: parsing runs inside
the upload request, off the event loop via `run_in_threadpool`. That is adequate
for the exports seen so far and would need revisiting for very large archives,
where a request-bound parse holds the connection for the whole read.

**The recording is kept.** Transcription is lossy and cannot be un-made: a
garbled sentence is unrecoverable if the original is gone, and a better model
next year cannot re-read a file that no longer exists. Audio is stored
content-addressed under `data/audio/` and the transcript is treated as derived.
Browser webm is the one exception to byte-for-byte storage: its container is
rewritten losslessly so playback can seek, which changes the stored bytes and
hash while leaving every audio sample identical.

**A date that was not read from the source records how it was chosen.** Dates
supplied by anything other than the importer's own parsers — a crosswalk built
from another export, a page's creation time, a resemblance to another entry —
are provenance, not facts, and a `certain` label on one cannot be audited from
the label alone. `data/imports/date-provenance.json` records, per batch and date
source, the rule that supplied it, its confidence and where the crosswalk lives.
Written when dates are enriched, not reconstructed afterwards.

**An unknown date is storable, and is not a date.** *(Amended 2026-09-19, at the
owner's request, for 43 voice transcripts whose export is lost.)* This ADR has
always said a date is read or it is absent, never invented — but until now the
second half had nowhere to live. `reflections.reflection_date` and
`theme_occurrences.occurred_at` were both `NOT NULL`, so "absent" was
unrepresentable and the commit refused any entry without a day. The rule was
sound; its enforcement was a wall rather than a record, and 318,000 characters
of the owner's thinking sat staged and unreadable behind it.

Both columns are now nullable, and an entry may be committed with no date once
the owner has explicitly marked it unknown (`import_items.date_unknown_accepted`).
Nothing about the prohibition changes. Unset is still refused — "the parser
found nothing" is not an answer, and the default for that flag is false, so an
export whose dates failed to parse is held for review exactly as before. What is
new is that the owner can answer *unknown*, and be believed.

Three things follow, and each is load-bearing:

- **No fallback may fill the gap.** `get_unassigned_embeddings` read
  `occurred_at or created_at`, which was harmless only while every entry had a
  date; the moment an undated one exists, that `or` dates it to the minute it
  was embedded, and nothing downstream can tell. The fallback is gone. A missing
  date stays missing, and each reader decides what it can measure.
- **Undated evidence reaches no window.** Six engines measure in days, and an
  occurrence with no date has no place in any of their arithmetic.
  `get_theme_occurrences` returns dated rows unless asked otherwise, so this is
  a property of one query rather than a null check repeated six times, where a
  single omission would be a wrong number nobody could see.
- **The counts stay apart.** `themes.occurrence_count` continues to mean
  occurrences that can be placed in time, because that is what every engine
  gates on; `undated_occurrence_count` is counted beside it and never summed
  into it unlabelled. The lifelong scale is the one reader that asks for both,
  and it reports a count with no span rather than a span it cannot support
  (ADR-0009).

**Order can be read even when dates cannot.** A transcript file numbers its
recordings; that numbering is stated by the source exactly as a date would be,
and it is kept in `reflections.entry_sequence`. It orders undated entries among
themselves and nothing derives a day from it — it is not a date at one remove.

**An absence is resolvable.** The reason storing one is acceptable is that the
owner can supply the day later, and `set_reflection_date` carries it through to
the occurrences the entry already has. Without that, answering the question
would change nothing they could see. It fills a blank only; a date already read
from the writing is never overwritten, which would be this ADR's prohibition
arriving through a different door.

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
embeddings and their occurrences, then refreshes the affected themes and deletes
any recording no remaining entry refers to — an undo that kept the audio would
keep the most personal part of what was imported.

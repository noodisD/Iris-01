# ADR-0015: One engine reads the entries, and must prove it read them

## Status
Accepted — 2026-09-18 · "Never stored" amended by [ADR-0016](ADR-0016-stored-candidates.md)

## Context
Every analytical engine counts. Trajectory counts occurrences per week, tension
counts days two themes share, resolution compares two windows. The owner looked
at eight cards reading "is dissipated · 0 in 21d · 0 in the 90d before" and said
they brought zero real insight, then described what one would look like: a
tendency in how they act, visible in how they write, rather than a count of
how often a subject comes up.

No counting engine can produce that. It is not a frequency, a rate, or a
co-occurrence. It is something a reader notices in the writing — and nothing in
IRIS had ever read the writing. The entries were embedded, clustered, and
counted, but never read.

The obvious fix is the dangerous one. A model handed someone's journal will
produce fluent, confident, unfalsifiable statements about them all day, and
they will read as insight precisely because they are about the person rather
than about their data.

## Decision
One engine (`agent/observations.py`) reads entries, and everything about it is
a constraint on what it may come back with.

**Which side of ADR-0003 it falls on.** It reads evidence and produces
something that is not evidence. It reads reflections the owner deliberately
logged, and only those still marked `evidence_eligible`. It never reads chat.
Its output is never stored, never embedded, never clustered, and never becomes
an occurrence — so it cannot feed back into the counting engines, and IRIS
still cannot talk itself into believing something.

**It runs only when asked.** `POST /api/observations` is the only caller, and
nothing inside IRIS calls the engine. A test asserts that the pipeline, the
chat core, the orchestrator and the insights service cannot reach it. The
owner's journal is never sent anywhere by a background job.

**Every claim carries quotes, and every quote is verified.** Each quoted string
must appear character for character in the stored entry it was attributed to,
with only whitespace allowed to differ. A quote that appears nowhere, or that
appears in a *different* entry than the one cited, drops the whole observation.
Nothing is repaired: a citation that needed fixing was not a citation.

**A claim resting on one entry is an anecdote**, and needs two entries before
it is called recurrent.

**Wording is filtered by `agent/narrative_policy.py`.** That module's `raise`
mode is for IRIS's own templates, where a forbidden word is a bug in code we
wrote. A model producing one is ordinary, so the claim is discarded and the
rest of the batch survives.

**It describes a span, not a present.** Each observation carries the first and
last day of writing it was drawn from and is phrased about that period, so it
never makes the present-tense claim that ADR-0007's coverage gate exists to
withhold.

**It passes the same admission policy as everything else** (ADR-0007): engine
enablement and the owner's confidence threshold apply, with confidence derived
from how many distinct entries and how much time the citations actually span.

## Consequences
IRIS can say something that sounds like a person noticed it, and every such
statement can be checked against the owner's own words in one click.

The engine is expected to return nothing fairly often, and that is a correct
answer rather than a failure to be tuned away. Loosening verification to fill
the screen would reintroduce exactly the failure this ADR exists to prevent.

Observations are not counted, so they never become the input to another
measure. A future feature that wants them stored has to reopen this ADR, and
must say what stops a model's own output from later being read back as though
the owner had written it.

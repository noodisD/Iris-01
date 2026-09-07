# ADR-0010: A journal entry is a reflection

## Status
Accepted — 2026-09-07

## Context
The same user concept had two stores. The SPA wrote `reflections` through
`ReflectionService`; the CLI wrote `journal_entries` through `JournalEntry`.
They were separate tables with separate source types and separate evidence
weights (`reflection` 1.0, `journal_entry` 0.9), so the same sentence counted
for more or less depending on which surface the user happened to type it into.

Neither surface could see the other's entries: `GET /api/journal` reads
reflections only, and the chat context assembled two builders — one per table —
that a reader could easily mistake for two different kinds of content. The
tables also disagreed about what an entry *is*: `journal_entries` had a
free-form `wellbeing_data` JSONB blob, while `reflections` had typed
`energy_level` and `clarity_level` columns with range constraints.

## Decision
A journal entry is a reflection. `JournalEntry` now formats the CLI's structured
prompts into text and delegates to `ReflectionService`, the same seam the HTTP
API writes through, so a CLI entry and a UI entry are indistinguishable
downstream — same table, same source type, same evidence weight, same mood
inference, same pipeline call. The duplicate chat-context builder is gone.

`journal_entries` is kept as a read-only legacy table. `scripts/backfill_journal_entries.py`
moves any rows it still holds into `reflections`, idempotently.

## Consequences
There is one answer to "what have I written", and one place a new field has to
be added.

Existing `embeddings` and `theme_occurrences` rows still reference
`('journal_entry', id)`. They are deliberately left alone: they are historical
evidence, correctly attributed to the row that produced them, and rewriting
their source would silently change conclusions the engines have already drawn.

The table therefore cannot be dropped yet — that needs a migration tool
(ADR-0008) — so `journal_entry` remains a valid source type in the data layer
and in test fixtures, and `EVIDENCE_WEIGHTS` keeps its entry. Nothing in the
product writes it. Code that adds a *new* write to `journal_entries` is a
regression against this ADR.

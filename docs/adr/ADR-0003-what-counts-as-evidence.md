# ADR-0003: Only deliberate logging counts as evidence

## Status
Accepted — 2026-09-06

## Context
Chat messages were embedded and matched against themes, and later clustered into
new ones. The effect was circular: mentioning a dissipated pattern created a
fresh occurrence of it, which invalidated the resolution cache, so the label
recomputed to "persisting" *before the narrative for that same turn was
written*. Talking about a pattern manufactured the evidence that it was still
present.

Skipped habits were embedded too, as `"Anchor: Yoga | … | Action: Skipped"` — a
vector dominated by the habit's own name — so not doing something reinforced the
theme for it, and trajectory could report a habit as increasing while it was
being abandoned.

Neither source was ever intended to count. `CONTEXT.md` defines an occurrence as
a journal entry, reflection or habit completion, and `EVIDENCE_WEIGHTS` has no
entry for messages — they were silently taking the 0.5 default meant for a bare
habit tick.

## Decision
Evidence is what the user deliberately logged: journal entries, reflections and
*completed* habits. Chat messages are embedded for semantic recall but never
become occurrences and are never clustered. Skipped habits do not enter the
analytical pipeline at all.

## Consequences
IRIS cannot talk itself into believing something. Conversation informs recall
without becoming proof.

Any new source type must state which side of this line it falls on, and adding
one to `get_unassigned_embeddings` without adding it to `EVIDENCE_WEIGHTS` is a
bug. A future feature that wants conversation to count as evidence has to
reopen this ADR, because the fix would otherwise arrive through the discovery
door rather than the matching door — which is precisely how the first fix here
turned out to be incomplete.

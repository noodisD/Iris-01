# ADR-0016: What reading finds is stored as a proposal, and counted only once confirmed

## Status
Accepted — 2026-09-19 · Amends ADR-0015's "never stored"

## Context
ADR-0015 said the reading engine's output is never stored, and that a feature
wanting it stored would have to reopen that decision and say what stops a
model's own output from later being read back as though the owner had written
it. That feature was built — discovery, candidates, confirmation — and the
decision was never reopened. For a week the engine's docstring, its endpoint
and the ADR all said "nothing is stored" while the code stored candidate
themes, their prototypes, and a record of every run with the model's raw
output. The review that walked the codebase found the contradiction; this
records the decision that was actually made.

There are two ways to read. `POST /api/observations` is a quick read that
returns findings and stores nothing — that part of ADR-0015 still holds.
`POST /api/constructs/discover` reads the whole archive and stores what it
finds, for the owner to review.

## Decision

**What is stored.** A discovery run writes:

- an `observation_runs` row: model, prompt version, passes planned and
  completed, status, error, and the raw pre-merge observations — so merging
  can be judged later without paying to read private writing again;
- for each surviving finding, a theme row with `origin = 'observed'` and
  `status = 'candidate'`, its claim in `definition`, and a `proposal_key` so a
  rerun cannot resurrect something the owner declined;
- its `theme_prototypes`: the owner's own sentences the claim was verified
  against.

**What stops the model's output being read back as the owner's writing.**

- *Nothing reads a candidate.* The engines take themes through `get_themes`,
  which admits `status = 'active'` only. A candidate is visible for review and
  invisible to every measure.
- *The reader reads entries, never themes.* Its input is reflections and staged
  imports (`get_entries_for_reading`, `get_staged_for_reading`); a claim, a
  definition or a run's raw output is never in that input.
- *A construct is anchored in the owner's sentences, not the model's.* Its
  centroid is built from the verified quotes, never from the claim text, and
  matching goes through the same comparison space as every theme.
- *Nothing is counted until the owner confirms it.* Confirmation writes
  occurrences, each recording why it was admitted: `citation` for a sentence the
  owner read while confirming, `similarity` for a match the detector proposed.
- *A claim is only confirmable as what its evidence can bear.* A verified quote
  proves the subject appears in the writing, so a construct counts mentions
  (`claim_kind = 'mention'`). Claiming a behaviour is refused at confirmation.
- *A quote must support the claim, not merely exist.* Every finding is checked,
  quote by quote, for whether each is an instance of the claim, contradicts it,
  or only mentions the subject (`check_support`). One contradiction drops the
  finding; mentions are not counted as support; and a check that cannot be
  made drops the finding rather than keeping it unchecked.

## Consequences
The owner can review what IRIS read, decline it once and have that stick, and
see for any counted occurrence whether they vouched for it.

The raw model output in `observation_runs` is a record, not an input. A future
feature that reads it back — to train, to summarise, to seed anything — reopens
this ADR.

Behaviour claims stay refused at confirmation until the support check has been
shown to hold on the owner's own archive, not only on invented cases. Lifting
that refusal is a decision to record here, not a flag to flip.

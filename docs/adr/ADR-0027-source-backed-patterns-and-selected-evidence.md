# ADR-0027: Patterns and selected conversations remain source-backed

## Status
Superseded for writing-derived Patterns and Insights by the process-first
personal-dynamics cutover below. ADR-0024 still governs measured days.

## Context
The prototype discovery pass could show plausible accounts without making it
clear which words were the owner's, which labels were provisional, or whether a
source had since changed. A difference assembled from two unequal groups of
occasions also needs its denominators, not just two co-label counts. Patterns,
Insights, and a conversation about either must refer to the same current record.

## Decision
Discovery reads eligible reflections through the durable ingest queue. Each
account's populated situation, response, optional demand, information, outcome
and owner explanation must resolve to passages in its verified citations;
missing parts remain missing. Actor, modality, domain and pattern labels are
provisional. Only a self-described, happened account with situation, response
and outcome is comparable. A provider or labelling failure does not publish a
partial reading. The worker publishes under a source-revision check; edits,
deletions, eligibility changes and extraction/library changes retire stale
readings. Discovery status exposes current, pending, failed and omitted work.
A recorded entry date is not proof of the occasion's date; undated accounts
belong only to the all-time range.

Patterns leads with the owner's passages, both outcome sides, review controls,
coverage and the library explanation separately. Rejected accounts remain
reviewable but leave the counts. Owner tone corrections and verdicts affect the
computed view; a note alone is not a positive verdict. A co-label difference
qualifies only with at least three accepted better and three accepted worse
accounts for its primary pattern, a co-label count gap of at least two and a
rate gap of at least 25 percentage points. Every denominator account is
inspectable with or without the other label. Two accounts from different
entries can instead be juxtaposed as an explicitly exploratory outcome pair,
not a trend. Measured-day comparisons retain ADR-0024's separate rules. None
of these comparisons establishes cause.

A selected discussion passes a typed pattern, outcome-pair, co-label or day
reference containing its range and snapshot, never client-supplied quotations.
The server resolves it against the owner's current source-backed evidence and
previews the material before a chat turn. On send it checks the snapshot again
and rejects a changed or no-longer-qualifying selection before saving a
message; the owner can review updated evidence and edit the draft. The model
gets a bounded server-selected context for the chosen evidence, not automatic
approval or a new analytical occurrence. Conversation does not change a
pattern or difference verdict.

## Consequences
The owner can trace every displayed account and denominator to a source and
correct labels without treating a model's interpretation as their own words.
New or edited writing is eventually consistent while the queue runs; a failed
provider leaves an explicit incomplete state rather than a silently complete
empty library. Smaller samples and equal-rate groups do not produce co-label
insights. A preview can expire between opening and sending, requiring an
explicit review instead of silently discussing stale evidence. This amends
the client-facing threshold and reading lifecycle in ADR-0023; the old
observation reader's on-request-only rule in ADR-0015 remains specific to
observations, not queue-backed discovery.

## Current cutover: process-first personal dynamics

The prior catalogue pattern labels, outcome-pair and co-label insight
pipelines were removed rather than adapted. Extraction keeps actor, record
kind, situation, response and independent immediate/later outcomes separate;
original cited paragraphs are necessary but insufficient until a contextual
field checker confirms each populated field. Failed checking is unavailable,
not an empty reading. Discovery proposes context–response dynamics without
seeing the process-lens library, checks memberships across the full eligible
archive, and treats retellings or unclear event identity conservatively.

Two independently identifiable self-events from two entries can establish
an emerging dynamic, three a recurring dynamic; a general self-report
remains owner-described, not an occurrence count. The 24 process lenses
annotate only after discovery, with source-grounded requirements and exclusions
and at most two matches. Insights distinguish sourced observation, the
owner's meaning, tentative possible meaning, rival explanation, contrary
accounts and unknowns; an outcome never follows from a later writing date.

The web and Android Patterns/Insights views use the same range, revision
and snapshot contracts. They offer account corrections and verdicts without
silently approving a note. Only typed current `dynamic`, `personal_insight`
and independent `day` references can enter discussion. Source revisions,
eligibility changes and corrections invalidate the derived view; a historical
provider response is never used as a current finding. The owner-only
diagnostic/reference process and separate provider-release gates are in
[`docs/reference-evaluation.md`](../reference-evaluation.md). Until the
independently reviewed holdout and backed-up archive cutover complete, this
decision describes the implementation, not verified archive coverage.

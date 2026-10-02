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

### Cost: ask each question once (2026-10-01)

As first built, a synthesis run re-proposed definitions from the whole archive
and re-asked every definition × account check and every account pair. The
model worded definitions slightly differently each time, so nothing could be
reused. By the code's own estimate the first run cost about $12, and every new
or edited entry about $11 again, growing with the archive.

The method and its gates are unchanged; the questions are asked once:

- **Remembered verdicts** (`agent/discovery_memo.py`, migration 0046). A
  membership, identity or equivalence verdict is kept under a hash of exactly
  what was asked: prompt and schema version, model, the definition's wording
  and the accounts' content fingerprints. It is kept only after validation. A
  changed source has a new fingerprint and is asked afresh, so this never
  turns a historical response into a current finding: it reuses the answer to
  the identical question about the identical text. Whole replies for the
  remaining stages (proposal, specificity, refinement, interpretation, claim
  checks, lens matching) are reused only for a byte-identical request, and a
  run that fails forgets the replies it kept.
- **Definitions carry forward.** The last draft from the same discovery
  version and model seeds the next run. Only accounts it never saw are read
  for new proposals, and every carried and new definition is still checked
  against every account.
- **Each account is shown once per request**, with up to 12 definitions to
  check against it, or with several accounts and the pairs among them in
  blocks, instead of once per row.
- **A row the model leaves out is asked again on its own.** A first run
  asks well over a thousand batches. On the owner's archive, the model
  repeatedly left one definition out of one account's 12-row request, and
  answered every other account in full. A batch's valid rows are kept and
  remembered; only the missing rows are asked again, alone, up to three
  times. A row still unanswered fails the stage, because unchecked is
  unavailable, never "not a member". The retry then asks only for that row.
  A failed check forgets only the whole reply that failed. An outage forgets
  nothing.

Estimated on the owner's archive (184 entries): the first run is at most
about $6. After that, a new entry costs about $0.05, and up to about $0.36
when it changes a dynamic's members and the interpretation is asked again.

### Model and tier (2026-10-02)

The worker passes run on `gpt-6-luna` on OpenAI's Flex tier
(`OPENAI_WORKER_MODEL`, `OPENAI_WORKER_SERVICE_TIER`). The owner chose this over
OpenRouter's cheaper open models: those would have saved well under a dollar
once, while sending the journal to a router and a third-party host. Flex is
the same model at half price. It is slower, and sometimes answers 429
"capacity unavailable", which is not charged; the client pauses and sends the
request again (15 s, 60 s, 180 s), then fails so the work queue retries later.
Thinking is left at the model's default, because quality comes first. On the
owner's archive (184 entries, 870 accounts, 161 of them comparable events),
the first run is at most about $1.40, then at most about $0.09 for each new
entry. Reading all 184 entries took 1,139 requests, about $0.21 and just
under two hours. In IRIS's earlier labelling test (2026-09-25),
gpt-5.6-terra was more conservative than luna and no more accurate, so a
larger model is not the quality lever here; the owner's verdicts are.

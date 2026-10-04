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

- **A row unclear on everything is not sent as evidence.** The matrix
  checks every account against every definition. On the owner's archive,
  869 of 870 rows for one definition were unclear on context, response and
  relation: the account does not speak to it. Refinement, the pattern
  write-up, the insight proposals and their claim checks sent all of them
  as source context,
  about 1.2 million characters in one request, so the run could not finish.
  They now send only rows that say something (support, exception, response
  elsewhere, mixed, or any non-unclear judgment). These rows are still
  checked, counted and stored. A refinement that still will not fit is
  skipped, and the definition stays as checked.

- **Every step re-asks what fails its check instead of failing the run.**
  Lens tagging keeps a batch's valid rows and asks again only for the rest;
  the pattern write-up, claim check and insight proposals are asked again
  whole. Before asking again, the failed reply is discarded, so it is not
  replayed from memory. A row or pair answered twice in one reply counts as
  unanswered, because a reply that contradicts itself is not a decision to
  choose from. What is still unanswered after three asks fails with the last
  problem seen, never as "no match".
- **Membership requests share accounts.** A definition rechecked against the
  whole archive after a refinement was asked one account per request: 870
  requests per refined definition, 6,962 in one attempt. Requests now hold up
  to 12 rows across accounts. The verdict key covers the rules for deciding
  a pair, not how requests are laid out, so the change kept the 32,088
  verdicts already paid for.

- **One subject's complete sources may pass the batching budget.** A long
  voice entry has no paragraph breaks, so its cited "paragraph" is the
  whole entry, about 21,000 characters. One pattern with four such
  supports needed 130,823 characters. A request holding a single subject
  (one pattern write-up, claim check, insight, definition or lens unit) may
  now go up to `SINGLE_SUBJECT_CHARS`, four times the batching budget and
  far inside the model's context. Several items are still packed within
  the batching budget, and past the cap a request still fails rather than
  being cut.

- **A claim that does not hold is withheld, not the pattern.** Three
  write-ups for one pattern stated an immediate result and cited the
  `immediate_outcome` field of a supporting self-report, which records only
  `self_report`. The whole pattern was discarded each time. As the claim
  check already withholds a failed hypothesis without discarding supported
  facts, the write-up now withholds an ungrounded result clause, or an
  ungrounded meaning together with its rival, and keeps the grounded
  context and response. Those two and the open question still must hold.
  Nothing ungrounded is published.

- **A lens that cannot be decided validly is withheld for that pattern.**
  Lens tags are optional editorial labels, and only positive matches are
  shown. On the archive the model kept quoting a `self_report` field on an
  event that records situation, response, feeling and concern. A lens/unit
  pair still undecided after three asks no longer fails the run. That lens
  is withheld for the pattern: it is never shown as matching, and no result
  is built from partial checks. An unreadable reply or an unavailable
  provider still fails the stage. This replaces omp's rule that any
  incomplete lens check fails the run. Withholding keeps that rule's intent,
  an incomplete check is never presented as a result, without letting one
  label stop every pattern from being published.

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

### Proposals must recur (2026-10-02)

The first full run published 7 patterns, all owner-described from a single
entry, with no insights. A comparison on 480 membership checks found that
the model was not the cause: gpt-5.6-terra agreed with gpt-6-luna on 479.
The checks were not too strict either: they confirmed 23 of the 24 examples
the proposer had named. The cause was the proposals. Each definition was
proposed from one event and worded around that occasion, so nothing else
could match it, and nothing recurred.

Each proposal request had shown accounts with their full source passages.
Long voice entries cite whole entries, about 21,000 characters each, so a
request held only a few entries and could not see anything recur.

- **Proposals are read from extracted fields** (situation, response, stated
  feeling, concern, explanation, outcomes, self-report), not from the
  passages. A request holds about half the archive across time. Every
  candidate is still checked against complete passages afterwards.
- **A candidate must recur.** It must name at least two events from
  different entries, or an explicit owner self-report of the general
  relationship. A candidate seen once is dropped before it costs a check.
- **Events and self-reports are proposed in separate passes.** Read
  together, self-reports (which state a habit outright) crowded out the
  events.
- **A new entry is read with the earlier accounts beside it.** A new
  candidate must name at least one new account.

Tried on the archive, proposal alone: 23 candidates, 8 of them recurring
across 2 to 5 entries' events, against none before.

## Bounded updates (2026-10-04)
The first therapy session (ADR-0028) proposed 22 new definitions. Each was
checked against all 885 accounts, one request at a time on Flex, and the update
ran for most of a day. Two changes bound it:
- An update adds at most five new definitions (`MAX_NEW_DEFINITIONS`).
  Definitions that had support keep their place, so one entry cannot push the
  owner's patterns out; carried definitions without support fill any room left
  up to 24. The status and import estimates count the new definitions and their
  one possible rewording.
- Membership and identity batches are asked six at a time
  (`CONCURRENT_REQUESTS`). Each is independent and kept as it lands, so this
  changes how long an update takes, not what it costs or decides.


## Distinct occasions and withheld titles (2026-10-05)
- The identity rule decides `distinct_events` from the details of each account
  (a different situation, people, place, action, outcome or stated time), and
  treats parts or retellings of one occasion as the same event across entries.
  The earlier "details must exclude identity" left half of all event pairs
  unclear, and an unclear pair never counts as a separate occasion.
- A pattern whose draft title fails its claim check keeps its checked context
  and response; the response stands in for the title.

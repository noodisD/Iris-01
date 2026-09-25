# IRIS Domain Context

IRIS is a local-first AI companion for one person. It runs on one machine, as
one process with one PostgreSQL database, for one local user with no login
(ADR-0001). It detects, verifies and prioritises long-term patterns in what that
person deliberately logs, under a strict **non-interpretive contract**: it
reports observations and the evidence behind them, never assumes causality, and
never offers unsolicited advice.

Every label and number below is what the code does. `tests/test_context_guards.py`
fails if a classifier emits a label this file does not name, or if an engine
list here and in the code disagree.

## Glossary

### Theme
A pattern recurring across what the owner logged: a group of occurrences that
say the same kind of thing.

**Properties:**
- `id`, `user_id`, `summary` (a natural-language name)
- `centroid_embedding` — 1536-dim vector the theme is matched against
- `origin` — `"clustered"` (found by the persistence engine) or `"observed"` (a construct, found by reading)
- `status` — `"active"`, `"candidate"` or `"rejected"`; only `"active"` themes are measured
- `claim_kind` — `"mention"` (appears in the writing) or `"behaviour"` (the thing happened); constructs can only be confirmed as mentions (ADR-0016)
- `occurrence_count` — occurrences that can be placed in time; `undated_occurrence_count` — those that cannot, counted beside it and never summed in (ADR-0013)
- `first_seen_at`, `last_seen_at` — the dated span; `span_is_undated` says the span means nothing when no occurrence is dated

**Invariants:**
- Themes are user-scoped
- Similarity is cosine on what differs between entries: once a user has `PERSISTENCE_STYLE_MIN_ENTRIES` (30) evidence embeddings, their average embedding — the voice every entry shares — is removed first (ADR-0014)
- ≥ `PERSISTENCE_STYLE_CLUSTER_THRESHOLD` (0.50) to form a new theme; ≥ `PERSISTENCE_STYLE_MATCH_THRESHOLD` (0.40) to join the *closest* existing theme
- Below 30 entries, raw cosine: ≥ `PERSISTENCE_CLUSTER_THRESHOLD` (0.78) to form, ≥ `PERSISTENCE_MATCH_THRESHOLD` (0.70) to join
- A clustered theme needs `PERSISTENCE_MIN_CLUSTER_SIZE` (5) entries to form, with every pair clearing the bar (complete linkage)

### Construct
A theme found by *reading* rather than clustering (`origin = "observed"`). The
reading engine proposes a claim with verbatim quotes; it is stored as a
`"candidate"` that nothing measures; the owner confirms or rejects it. Its
centroid is built from the owner's own quoted sentences, never from the claim.
A rejection is remembered by `proposal_key`, so a rerun cannot propose it again.

### Occurrence
An instance of a theme in one source.

**Properties:**
- `theme_id`, `source_type` (`"reflection"`, `"habit_completion"`, `"pixel_location"`, `"fitbit_sleep"`, etc.), `source_id`
- `occurred_at` — when the source happened; **null** for writing that carries no date (ADR-0013)
- `snippet` — the owner's own words from the entry, or a factual description of a measurement
- `admission_basis` — `"citation"` (something the owner read and confirmed — a sentence, or a measurement), or `"similarity"` (a match a detector proposed)

**Invariants:**
- One occurrence per theme × source
- Every engine that measures in days reads dated occurrences only; lifelong is the one reader that also counts undated ones
- Chat messages are embedded for recall and are never occurrences (ADR-0003)

### Source
Evidence comes from owner-authored reflections (including journal entries,
ADR-0010), completed habits, and sensor readings the owner explicitly links
to an existing theme during review (ADR-0017). The old `journal_entries`
table was dropped; sensors are measurements, not reflections.

A reflection's `reflection_date` may be **null**: the owner said the day is not
known. It is recalled and read, counted without a span, and kept out of every
window until a date is supplied (`set_reflection_date`), which dates its
occurrences too.

A paired Android app sends batches to an isolated TLS mobile intake. Staging
does not create evidence. On confirmation readings enter
`sensor_observations`; only owner-approved source-to-theme links produce
capped `theme_occurrences`. The latest approved reading per source, theme
and UTC day occupies the cap; deletion restores an older approved reading
when one exists. Unlinked readings stay raw and cannot form themes.
Date-only step readings retain their calendar day in review.

### Trajectory
Whether a theme's recent rate differs from its baseline:
`TRAJECTORY_RECENT_DAYS` (14) against the prior `TRAJECTORY_BASELINE_DAYS` (60).

**Labels:**
- `"insufficient data"` — fewer than `TRAJECTORY_MIN_DATA_POINTS` (3) occurrences; a non-finding, never shown
- `"emerging"` — first seen within the last 30 days, with activity in the recent window
- `"increasing"` / `"fading"` — the rate moved up / down by more than `TRAJECTORY_DELTA_THRESHOLD` (0.05), or, when the rate is flat, the weekly slope did
- `"stable"` — neither

### Resolution
Whether a theme has gone quiet, settled, or come back: `RESOLUTION_RECENT_DAYS`
(21) against the prior `RESOLUTION_BASELINE_DAYS` (90). Cached for
`RESOLUTION_CACHE_TTL_HOURS` (24).

**Labels:**
- `"dissipated"` — `past_count ≥ RESOLUTION_MIN_DATA_POINTS` (3) and nothing recent
- `"reappearing"` — the same baseline, recent activity, and a gap between them
- `"unsupported"` — both windows empty, or no dated occurrence at all; a non-finding, never shown
- `"stabilized"` — both windows non-empty and the relative change within `RESOLUTION_DELTA_EPSILON` (0.05)
- `"persisting"` — otherwise

### Tension
Two themes (always a pair) that appear on the same *days* while their
trajectories move in opposite directions — shared days, because clustering puts
an entry in one theme. Recent `TENSION_RECENT_DAYS` (14), baseline
`TENSION_BASELINE_DAYS` (60).

**Labels:** `"persistent"` (stability ≥ `TENSION_MIN_STABILITY` (0.3) and recent
activity), `"emerging"` (recent only), `"fading"` (past only), `"intermittent"`.
Each theme needs `TENSION_MIN_OCCURRENCES` (5); the pair needs
`TENSION_MIN_COOCCURRENCE` (3) shared days and divergence ≥
`TENSION_MIN_DIVERGENCE` (0.05).

### Leverage
Temporal association, **not cause**: whether theme A is followed by theme B
within `LEVERAGE_TIME_LAG_DAYS` (7) more often than B by A, over
`LEVERAGE_WINDOW_DAYS` (60). Always a pair, labelled `"associated"`.

**Invariants:** both themes need `LEVERAGE_MIN_OCCURRENCES` (5); the pair needs
`LEVERAGE_MIN_CO_OCCURRENCES` (3); `directional_lift` must reach
`LEVERAGE_ASYMMETRY_THRESHOLD` (0.15). Same-day occurrences are neutral.

### Decision Impact
Whether a target theme's rate changed in the `DECISION_IMPACT_WINDOW_DAYS` (14)
after each occurrence of an anchor theme, against the prior
`DECISION_IMPACT_BASELINE_DAYS` (60). Association over time, not cause.
Directions: `"increase"`, `"decrease"`, `"emergence"`, `"fade"` (and `"none"`,
which is not reported). Incomplete follow-up windows are right-censored.

### Lifelong
A theme's occurrences across the whole record: how many, between which dates,
across how many months, which year holds most, and how long since the last.
Never claims the present, so the coverage gate lets it through.

**Labels:** `"spread"` or `"concentrated"` (at least
`LIFELONG_CONCENTRATION_SHARE` (0.6) of dated occurrences in one year), and
`"undated"` for a count over writing that has no dates — reported with no span.
Needs `LIFELONG_MIN_OCCURRENCES` (3) over at least `LIFELONG_MIN_SPAN_DAYS` (90).

### Observation
What the reading engine (`agent/observations.py`) noticed, with quotes. It runs
only when the owner asks, reads evidence only, never chat.

**Invariants:**
- Every quote is found verbatim in the entry it cites, or the whole finding is dropped
- Every quote supports the claim: a contradicting quote drops the finding, a quote that only mentions the subject is not counted, and a check that cannot be made drops the finding
- Two distinct entries at least; causal or prescriptive wording is dropped
- A quick read (`POST /api/observations`) stores nothing; discovery stores candidates and a run record (ADR-0016)

### Confidence
How much evidence stands behind a finding (`agent/confidence.py`).

- `sufficiency` — log-scaled weighted count against `CONF_HIGH_POINTS` (10); `recency` — exponential decay over `CONF_RECENCY_DAYS` (30); `consistency` — share of the dominant direction, when there is a direction
- Score weights: sufficiency 0.4, consistency 0.4, recency 0.2 (consistency's weight is redistributed when there is no direction)
- `"high"` — at least `CONF_HIGH_POINTS` weighted points, recency ≥ 0.5, a span of at least `CONF_MIN_COVERAGE_DAYS_FOR_HIGH` (7) days, and consistency ≥ `CONF_CONSISTENCY_THRESHOLD` (0.7) where there is a direction
- `"medium"` — at least `CONF_MIN_POINTS` (3)
- `"low"` — otherwise, or whenever recency < 0.2
- A theme's stored confidence is recomputed once older than `CONFIDENCE_CACHE_TTL_HOURS` (24), and computed on request for an explanation
- Dissipation is scored separately, on the silence and the logging around it

### Evidence
The facts a finding was computed from, append-only, time-stamped together:
`evidence_type` (`"count"`, `"rate"`, `"delta"`, `"window"`, …), `key`, `value`,
`engine_name`. Evidence supports or refutes; it never interprets.

### Admission (Meta-Control)
One function decides what IRIS has noticed, for chat and the Insights screen
alike (`agent/pipeline_orchestrator.py`, ADR-0007):

1. **Collection** — trajectory, tension, resolution, leverage (pairs), decision impact, lifelong; one grain each
2. **Coverage gate** — a finding about the present needs `COVERAGE_MIN_OBSERVED_DAYS` (3) days written in the last 21; findings about a span are exempt; `"unsupported"` and `"insufficient data"` are dropped
3. **Enablement gate** — engines the owner switched off
4. **Confidence gate** — below the owner's `min_confidence` (default `"medium"`)
5. **Conflict suppression** — incompatible findings on the same pattern, among those of at least medium confidence (e.g. `"dissipated"` resolution with `"increasing"` trajectory)
6. **Ranking** — confidence, recency, novelty and engine weight, with a deterministic tie-break

Chat then keeps one finding per pattern (a pair is its own pattern) and cuts to
the owner's `max_items`; the screen shows everything. Each gate records what it
held back and why.

### Narrative
A finding rendered as a sentence from a fixed template, then checked against a
firewall of causal and prescriptive words (`agent/narrative_policy.py`); a
sentence that fails is dropped, never rewritten. Templates quote the counts and
windows that were measured ("appeared 5 times in the last 14 days, against 2 in
the 60 days before"). The firewall also runs on the Insights read and on the
weekly letter.

### Pipeline (ingest)
A write stores the entry and its queue row in one transaction (ADR-0011); the
worker embeds it, matches it to the closest theme (or discovers new ones), lets
confirmed constructs classify it, and refreshes the cross-theme caches. Chat and
Insights then read through admission.

### User Preferences
- `enabled_engines` — a list of engine names, or null for all; the selectable engines are trajectory, tension, resolution, leverage, decision_impact, lifelong and observations
- `min_confidence` — `"low"`, `"medium"` (default) or `"high"`
- `max_items` — 1–10 (default 5): how many findings chat may raise; the screen is not limited

Set from Settings or the CLI's `/settings`; both write `user_preferences`.

### Idea
A substantive proposition — including a normative principle — that the owner
endorses, questions, or opposes in their own writing. A topic word, an inferred
trait, and a quotation of another author with no position of the owner's are
not ideas. One verified passage is enough. The statement does not change once
proposed; a changed proposition is another idea. This is not a psychological
engine and is not selectable in Settings (ADR-0021).

**Domain** is one organising category: philosophy, economics, trading, politics,
ethics, learning, or other. A trading pattern, method, edge, or practice is
trading, not economics. Economics is how an economy works. A skill, a craft, or
the time mastery takes is learning. A claim about freedom, dependence, or how a
life should be ordered is philosophy. Other is only for a position that fits
none of those areas.

**Citation stance** is what that passage expressed: `"endorsed"`,
`"questioned"`, or `"opposed"`. A check may also answer `"not_stated"`, which
is not stored. The date is the day the passage was written, or absent — never
the day a belief began.

**Present position** is the owner's current selection: `"exploring"`,
`"endorsed"`, or `"opposed"`. Confirmation starts at exploring unless they
choose otherwise. Old writing never sets it.

**Link** is a typed connection the owner confirmed, or a proposal waiting for
that confirmation: `"supports"`, `"contradicts"`, `"refines"`, or
`"depends_on"`. Iris may propose one. It is not a claim the journal stated
the connection.

**Tension** here is an accepted contradiction between two ideas the owner
currently holds. It is not the psychological tension engine. Moving either
position off `"endorsed"` removes the tension and keeps the edge.

**Critique** is Iris's on-request challenge of one argument: objections,
possible premises, and unverified suggestions of related thought. It is
labelled as Iris's, stored apart from the writing, and never becomes an idea,
a link, or evidence.

---

## Seams

1. **Evidence** — each engine emits its own facts through `emit_evidence()`.
2. **Confidence** — `ConfidenceEngine.compute_confidence()`.
3. **Conflicts** — the rules in `agent/conflicts.py`.
4. **Narrative** — `agent/narrative_templates.py`: one template per engine, or named variants chosen by the finding's `template_variant` (lifelong's `"undated"` and `"with_undated"`).
5. **Model** — `agent/intelligence.py` calls OpenAI; `stream()` for chat replies. There is no second provider.

---

## Key Invariants

1. **Non-interpretive** — IRIS reports what was observed and measured, never a cause or a recommendation
2. **One user, one machine** — no login, no cross-user data (ADR-0001)
3. **Sources are the owner's** — an entry changes only when the owner edits it (which re-derives everything from it) or supplies a missing date
4. **A date is read or absent, never invented** (ADR-0013)
5. **One admission** — chat and the screen cannot disagree about what IRIS noticed (ADR-0007)
6. **Transparency** — every suppressed finding is recorded with its reason

---

## Time Windows

- **Trajectory**: recent 14 days, baseline the prior 60
- **Resolution**: recent 21 days, baseline the prior 90
- **Tension**: recent 14 days, baseline the prior 60
- **Leverage**: 60-day window, lag up to 7 days
- **Decision impact**: 14 days after each anchor, against the prior 60
- **Coverage**: 3 days written in the last 21
- **Lifelong**: the whole record
- **Confidence recency**: decays over 30 days

---

## Evidence Weights

- **Reflection**: 1.0
- **Journal entry**: 0.9
- **Habit completion with notes**: 0.8
- **Habit completion (tick only)**: 0.5

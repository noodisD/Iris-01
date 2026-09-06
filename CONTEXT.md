# IRIS Domain Context

IRIS is a local-first, multi-user AI companion that detects, verifies, and prioritizes long-term behavioral patterns. It operates under a strict **non-interpretive contract**: observe and report evidence, never assume causality or offer unsolicited advice.

## Glossary

### Theme
A pattern identified across journal entries, reflections, and habits. Represents a semantic cluster of related occurrences.

**Properties:**
- `id` — unique identifier
- `user_id` — owner
- `vector` — 1536-dim semantic embedding (pgvector)
- `summary` — natural language name (e.g., "Stress", "Deep focus")
- `created_at` — timestamp of first occurrence

**Invariants:**
- Every theme has at least one occurrence
- `themes.created_at ≤ min(occurrences[*].occurred_at)`
- Themes are user-scoped (no cross-user themes)
- Semantic similarity score (cosine) ≥ `PERSISTENCE_CLUSTER_THRESHOLD` (0.78) to form a new theme
- Matching score (cosine) ≥ `PERSISTENCE_MATCH_THRESHOLD` (0.70) to add to existing theme

### Occurrence
An instance of a theme appearing in a source (journal entry, reflection, habit completion).

**Properties:**
- `theme_id` — which theme this instantiates
- `source_type` — "journal_entry", "reflection", "habit_completion", or "habit_completion_with_notes"
- `source_id` — ID of the source in its table
- `occurred_at` — timestamp (ISO 8601)
- `evidence_weight` — reliability of this source (0.5–1.0 depending on source_type)

**Invariants:**
- `occurred_at` must be ≤ `now()`
- Evidence weight follows `EVIDENCE_WEIGHTS` policy
- No duplicate occurrences (same theme × source × occurred_at)

### Source
Raw data that contributes to pattern detection. Types: journal entries, reflections, habit completions.

**Properties vary by type:**
- **Journal Entry**: raw_text, created_at, vector (pgvector), wellbeing_data
- **Reflection**: mood, energy_level, content, reflection_date
- **Habit Completion**: habit_id, completed_at, notes (optional)

**Invariants:**
- Sources are immutable once created (except soft deletes)
- Sources are user-scoped
- Raw text is never empty for journal entries

### Trajectory
Directional trend of a theme: is it increasing, decreasing, stable, emerging, or fading?

**Properties:**
- `label` — one of: "increasing", "decreasing", "stable", "emerging", "fading"
- `slope` — linear regression slope over the analyzed window
- `recent_rate` — frequency (count/day) in last `TRAJECTORY_RECENT_DAYS` (14)
- `baseline_rate` — frequency (count/day) in prior baseline window
- `confidence_level` — "low", "medium", "high"

**Invariants:**
- Requires ≥ `TRAJECTORY_MIN_DATA_POINTS` (3) occurrences to classify
- Slope is calculated only if ≥ `TRAJECTORY_MIN_SLOPE_POINTS` (2) time-distributed points
- "emerging" is special: zero baseline occurrences, recent_rate > 0
- "fading" is special: zero recent occurrences, baseline_rate > 0

### Resolution
State of a theme: is it dissolving, stabilizing, persisting, or reappearing?

**Properties:**
- `label` — one of: "dissipated", "stabilized", "persisting", "reappearing"
- `attenuation_score` — (1.0 - recent_rate / baseline_rate), clamped [-1.0, 1.0]
- `recent_count` — occurrences in last `RESOLUTION_RECENT_DAYS` (21)
- `past_count` — occurrences in prior baseline
- `confidence_level` — "low", "medium", "high"

**Invariants:**
- "dissipated": `past_count ≥ RESOLUTION_MIN_DATA_POINTS` AND `recent_count == 0`
- "reappearing": `past_count ≥ RESOLUTION_MIN_DATA_POINTS` AND `recent_count > 0` AND gap_detected
- "stabilized": `|attenuation_score| ≤ RESOLUTION_DELTA_EPSILON` (0.05)
- "persisting": fallback for all other cases

### Tension
Co-occurrence of two or more themes that show contrasting behavioral signals (e.g., one rising while another falls).

**Properties:**
- `pattern_ids` — set of theme IDs (typically 2, may be > 2)
- `co_occurrence_count` — # of overlapping windows (recent + baseline)
- `divergence_score` — measure of how differently they're trending
- `stability` — consistency of this pattern across time windows
- `confidence_level` — "low", "medium", "high"

**Invariants:**
- Must have ≥ `TENSION_MIN_COOCCURRENCE` (3) overlapping windows
- Each theme in tension must have ≥ `TENSION_MIN_OCCURRENCES` (5) total occurrences
- Themes must show divergence (trajectory directions differ)
- Stability must be ≥ `TENSION_MIN_STABILITY` (0.3)

### Leverage
Directional influence: pattern A tends to precede or cause changes in pattern B.

**Properties:**
- `source_id` — upstream theme (moves first)
- `target_id` — downstream theme (moves in response)
- `directional_lift` — P(B|A) - P(A|B), captures asymmetry
- `time_lag_days` — max lag between source occurrence and target (≤ `LEVERAGE_TIME_LAG_DAYS`, 7)
- `confidence_level` — "low", "medium", "high"

**Invariants:**
- Source and target must be distinct themes
- Both must have ≥ `LEVERAGE_MIN_OCCURRENCES` (5) total
- Co-occurrences (A then B within lag) ≥ `LEVERAGE_MIN_CO_OCCURRENCES` (3)
- `|directional_lift| ≥ LEVERAGE_ASYMMETRY_THRESHOLD` (0.15) to qualify

### Confidence
Reliability score for any insight (trajectory, resolution, tension, etc.).

**Properties:**
- `confidence_level` — "low", "medium", "high"
- `confidence_score` — float [0.0, 1.0]
- `data_points_count` — # of occurrences contributing to this insight
- `time_coverage_days` — span from first to last occurrence
- `consistency_score` — regularity of occurrences over time
- `recency_score` — how recent the contributing data is

**Scoring Weights:**
- Sufficiency (data volume): 40%
- Consistency (regularity): 40%
- Recency (freshness): 20%

**Classification Thresholds:**
- `data_points_count < CONF_MIN_POINTS` (3) → "low"
- `data_points_count < CONF_MEDIUM_POINTS` (5) → "medium"
- `data_points_count ≥ CONF_HIGH_POINTS` (10) → potentially "high" (if consistency strong)

### Evidence
Concrete facts supporting a classification decision.

**Properties:**
- `evidence_type` — "count", "rate", "delta", "gap", "stability", etc.
- `key` — name of the fact (e.g., "recent_count", "attenuation_score")
- `value` — numeric or boolean value
- `engine_type` — which analytical engine produced this (e.g., "resolution")

**Invariants:**
- Evidence is immutable (append-only log)
- All evidence for a single insight is time-stamped together
- Evidence supports or refutes a conclusion; never interpretive

### Insight
An analyzed finding from the pipeline: a theme with a computed label and confidence.

**Properties:**
- `engine_name` — which analytical engine produced it ("trajectory", "resolution", "tension", "leverage", etc.)
- `pattern_type` — "theme", "pair" (for tensions/leverage)
- `pattern_id` — ID(s) of the theme(s)
- `label` — computed classification (e.g., "dissipated", "increasing")
- `confidence_level` — "low", "medium", "high"
- `confidence_score` — float [0.0, 1.0]
- `timestamp` — when this insight was computed

**Invariants:**
- Every insight traces back to at least one Confidence record
- Confidence is computed fresh for each analysis run (no caching of confidence itself)
- Insights are user-scoped

### Meta-Control Layer
System of gates and filters that prevent inappropriate insights from reaching the LLM.

**Components:**

1. **Enablement Gate** — checks user preferences for which engines to run (e.g., "disable tension")
2. **Confidence Gate** — filters insights below `CONFLICT_MIN_CONFIDENCE` ("medium" by default)
3. **Conflict Suppression** — silences logically incompatible insights (e.g., can't be both "reappearing" and "dissipated")
4. **Prioritization** — ranks remaining insights by confidence, recency, novelty, and engine weight
5. **Budget Gate** — slices to top-K insights (default 5, user-configurable)

**Invariants:**
- Gates are applied in order (enablement → confidence → conflict → prioritization → budget)
- Each gate logs its suppressions for transparency
- User preferences override all gates (can enable disabled engines, raise/lower confidence thresholds)
- No gate is allowed to modify insight data; only filter or re-order

### Narrative
Natural language formatting of an insight for human consumption.

**Properties:**
- `text` — formatted string describing the insight
- `source_label` — computed label (e.g., "dissipated")
- `theme_id` (or pattern_id) — which pattern this describes
- `safety_checked` — boolean (narrative passed validation)

**Invariants:**
- Narrative must not speculate or assign causality
- Narrative must cite the evidence (e.g., "appeared 5 times in the past but 0 times recently")
- Narrative length is bounded (safety check)
- Narrative uses project vocabulary (terms from CONTEXT.md)

### Journal Entry
User's raw textual data: a message, reflection, or note.

**Properties:**
- `id` — unique identifier
- `user_id` — owner
- `raw_text` — the content (immutable)
- `created_at` — timestamp
- `vector` — pgvector embedding for semantic search
- `wellbeing_data` — optional dict of mood, energy, etc.

**Invariants:**
- `raw_text` is never empty
- `created_at` ≤ `now()`
- User can only read/write their own entries

### Pipeline
The full analysis workflow: ingest → embed → analyze → gate → prioritize → narrative → LLM.

**Stages:**
1. **Persistence Engine** — cluster new entries into themes
2. **Trajectory Engine** — compute directional trends
3. **Tension Engine** — detect conflicting co-occurrences
4. **Resolution Engine** — determine if patterns are fading/strengthening
5. **Leverage Engine** — find directional influence
6. **Decision Impact Engine** — measure effects of anchored decisions
7. **Meta-Control Layer** — apply gates and filters
8. **Narrative Formatter** — convert insights to text
9. **Intelligence Service** — send context to LLM

**Invariants:**
- Pipeline is user-scoped (no cross-user data leaks)
- Each stage produces artifacts that the next stage consumes
- No stage modifies source data
- Pipeline is deterministic: same input → same output

### User Preferences
Settings that override pipeline behavior.

**Properties:**
- `enabled_engines` — which analytical engines to run (list of booleans)
- `confidence_threshold` — minimum confidence to include insights ("low", "medium", "high")
- `max_items` — max insights in the LLM context (default 5)
- `conflict_suppression_enabled` — boolean

**Invariants:**
- Preferences are user-scoped
- Changes take effect on the next chat invocation
- Preferences never override safety constraints (e.g., can't suppress "low" confidence as a default)

---

## Seams (Interfaces for Variation)

### 1. Evidence Calculation
**Where:** Any analytical engine (Trajectory, Resolution, etc.)
**What varies:** How evidence is collected and weighted
**Current adapters:**
- Trajectory uses recency + slope + consistency
- Resolution uses raw occurrence counts + rates
- Leverage uses co-occurrence asymmetry

**How to adapt:** Create a new engine or override `emit_evidence()` to change what facts are considered.

### 2. Confidence Scoring
**Where:** `ConfidenceEngine`
**What varies:** How to combine data sufficiency, consistency, and recency into a single score
**Current adapter:** Weighted average (40/40/20)

**How to adapt:** Override `compute_confidence()` to use different weights or additional factors.

### 3. Conflict Detection
**Where:** `ConflictSuppressionEngine`
**What varies:** Which insight combinations are considered incompatible
**Current adapter:** Hard-coded rules (e.g., "dissipated" vs "reappearing")

**How to adapt:** Override `suppress()` to add new incompatibilities or make existing ones conditional.

### 4. Narrative Template Selection
**Where:** `NarrativeFormatter`
**What varies:** How insights are converted to human text
**Current adapters:** Template per label (e.g., dissipated → "appeared frequently in the past but has not appeared recently")

**How to adapt:** Add new templates or switch template sources in `format_insight()`.

### 5. LLM Provider
**Where:** `Intelligence` service
**What varies:** Which LLM backend to call (OpenAI, Gemini, local)
**Current adapters:** OpenAI (primary), Gemini (fallback)

**How to adapt:** Implement new adapter class inheriting from base LLM interface, register in `Intelligence.__init__()`.

---

## Key Invariants

1. **Non-Interpretive Contract** — IRIS reports observations and evidence, never assigns causality
2. **User Scoping** — All data and computations are scoped to a single user; no cross-user leakage
3. **Immutability of Sources** — Journal entries, reflections, and habit completions are never modified after creation
4. **Determinism** — Same input always produces the same analytical output (except LLM responses)
5. **Locality of Change** — Changes to one module's logic don't break other modules (via seams)
6. **Transparency** — Every suppressed insight is logged with its reason; users can audit what was hidden

---

## Time Windows (Temporal Contracts)

These are central to how IRIS distinguishes "recent" from "historical" patterns:

- **Trajectory Analysis**: Recent = last 14 days, Baseline = prior 60 days
- **Resolution Analysis**: Recent = last 21 days, Baseline = prior 90 days
- **Tension Analysis**: Same as Trajectory (14/60)
- **Leverage Analysis**: Window = 60 days, time lag = up to 7 days
- **Confidence Decay**: Evidence older than 30 days loses exponential weight
- **Recency Scoring**: Recent insights (< 30 days) get higher priority

---

## Evidence Sources (Reliability Weights)

IRIS weights different source types by credibility:

- **Reflection** (explicit mood/energy/emotion): 1.0x weight
- **Journal Entry** (detailed narrative): 0.9x weight
- **Habit with Notes** (context provided): 0.8x weight
- **Habit Tick Only** (default completion): 0.5x weight

Weights are applied during evidence aggregation to ensure reflections have more influence than quick habit ticks.

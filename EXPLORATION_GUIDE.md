# IRIS Module Exploration Guide

A structured path to understand IRIS from bottom up: data → analysis → control → output.

---

## Foundation (Start Here)

These modules establish the data layer and patterns used everywhere else.

### Phase 1: Database & Persistence Layer
**Why:** Everything flows through the database. Understanding the schema is foundational.

**Files to explore:**
1. `agent/database.py` (110KB)
   - Entry point: the `Database` singleton (`db`)
   - Learn: schema definition, connection pooling, query helpers
   - Key sections: `get_connection()`, the repositories, and the pooling in `_init_pool()`.
     The schema itself lives in `migrations/`, not here

2. `CONTEXT.md` — Domain glossary
   - Read the entire "Glossary" section (Theme, Occurrence, Source, Resolution, etc.)
   - Read "Invariants" section (what must always be true)

3. `agent/repositories.py` (40KB)
   - 14 repository classes (UserRepository, ThemeRepository, ResolutionRepository, etc.)
   - Pattern: Each repo handles one entity type, provides CRUD + query methods
   - Example: `ThemeRepository.get_theme()`, `ThemeRepository.get_occurrences()`

**Time estimate:** 60–90 min
**Verify understanding:**
- Can you describe what a Theme is and how Occurrences relate?
- Can you name 5 repository classes and what they do?
- What's the difference between pgvector and PostgreSQL in IRIS?

---

### Phase 2: Core Orchestrator
**Why:** This is the main entry point. It ties together all services.

**Files to explore:**
1. `agent/core.py` (397 lines)
   - Entry point: `PersonalAICompanion` class
   - Learn: how initialization works, how `chat()` flows, what `_get_aggregated_context()` does
   - Key methods:
     - `__init__()` — what services are initialized
     - `chat(message)` — the main pipeline
     - `_get_aggregated_context()` — how insights are gathered and filtered

2. `agent/pipeline_orchestrator.py` (250+ lines)
   - `AnalysisPipeline` class: runs all analytical engines in sequence
   - Key methods: `register_engine()`, `register_gate()`, `run(prefs)`
   - Learn: the gate system (enablement → confidence → budget)

3. `agent/constants.py`
   - All the tuning parameters (time windows, thresholds, weights)
   - Important: `RESOLUTION_RECENT_DAYS=21`, `TRAJECTORY_RECENT_DAYS=14`, confidence weights

**Time estimate:** 45–60 min
**Verify understanding:**
- What are the 6 analytical engines, in priority order?
- What happens inside `_get_aggregated_context()`?
- What's the difference between an "engine" and a "gate"?

---

## Analytical Layer (Core Logic)

These 6 modules answer specific questions about patterns. Study them in this order (depends on complexity + data).

### Phase 3: Persistence Engine (Clustering)
**Question:** "What patterns keep recurring?"

**Files:**
1. `agent/persistence.py` (350+ lines)
   - Entry point: `PersistenceEngine.get_persistent_themes()`
   - Learn: clustering via scikit-learn, similarity scoring, proto-theme formation
   - Key concepts:
     - `PERSISTENCE_MATCH_THRESHOLD=0.70` (add to existing theme)
     - `PERSISTENCE_CLUSTER_THRESHOLD=0.78` (create new theme)
     - `PERSISTENCE_MIN_CLUSTER_SIZE=5` (proto-theme boundary)

**Related:**
- `agent/pipeline.py` — `generate_embedding()` function (converts text to vector)

**Time estimate:** 60 min
**Verify understanding:**
- How does IRIS decide whether a new entry belongs to an existing theme vs. creates a new theme?
- What's a proto-theme?
- Why does IRIS use cosine similarity for clustering?

---

### Phase 4: Trajectory Engine (Trend Analysis)
**Question:** "Is this pattern increasing, decreasing, or stable?"

**Files:**
1. `agent/trajectory.py` (250+ lines)
   - Entry point: `TrajectoryEngine.analyze_theme(theme_id)`
   - Learn: linear regression, rate calculation, temporal windows
   - Key metrics:
     - `recent_rate` vs `baseline_rate` (slopes)
     - Direction labels: "increasing", "decreasing", "stable", "emerging", "fading"

**Related:**
- Time windows in `constants.py` (TRAJECTORY_RECENT_DAYS=14, BASELINE_DAYS=60)

**Time estimate:** 45 min
**Verify understanding:**
- How does IRIS calculate the slope of a theme?
- What's the difference between "emerging" and "increasing"?
- What data quality is needed to classify a trajectory?

---

### Phase 5: Resolution Engine (Dissipation Detection)
**Question:** "Is this pattern fading, stabilizing, persisting, or reappearing?"

**Files:**
1. `agent/resolution.py` (290 lines)
   - Entry point: `ResolutionEngine.analyze_theme(theme_id)` and `format_for_context()`
   - Learn: gap detection, attenuation scoring
   - Key logic in `_classify_resolution()`:
     - Dissipated: past_count ≥ 3, recent_count == 0
     - Reappearing: past_count ≥ 3, recent_count > 0, gap_detected
     - Stabilized: |attenuation_score| ≤ 0.05
     - Persisting: fallback

**Time estimate:** 45 min
**Verify understanding:**
- What makes a pattern "dissipated" vs "reappearing"?
- How does IRIS detect a gap?
- Why is the recent window 21 days instead of 14?

---

### Phase 6: Tension Engine (Conflict Detection)
**Question:** "What themes co-occur but show conflicting signals?"

**Files:**
1. `agent/tension.py` (250+ lines)
   - Entry point: `TensionEngine.analyze_all_tensions()`
   - Learn: co-occurrence detection, divergence scoring
   - Key logic:
     - Requires ≥ 3 overlapping windows with co-occurrence
     - Themes must show contrasting trajectory directions
     - Stability ≥ 0.3 to qualify

**Time estimate:** 45 min
**Verify understanding:**
- How does IRIS detect that two themes "conflict"?
- What's a co-occurrence window?
- Why is stability important for tensions?

---

### Phase 7: Leverage Engine (Influence Detection)
**Question:** "Which patterns tend to influence others?"

**Files:**
1. `agent/leverage.py` (320+ lines)
   - Entry point: `LeverageEngine.analyze_high_leverage_sources()`
   - Learn: directional asymmetry, temporal precedence, lift scoring
   - Key metric: `directional_lift = P(B|A) - P(A|B)`

**Time estimate:** 60 min
**Verify understanding:**
- What does "leverage" mean in IRIS (not power, not control)?
- How does IRIS measure if A "influences" B?
- What's the time lag window?

---

### Phase 8: Decision Impact Engine
**Question:** "Did a decision (anchor event) cause changes in other patterns?"

**Files:**
1. `agent/decision_impact.py` (350+ lines)
   - Entry point: `DecisionImpactEngine.compute_impact()`
   - Learn: pre-anchor baseline vs post-anchor observation
   - Key concepts: anchor events, relative delta, impact scoring

**Time estimate:** 60 min
**Verify understanding:**
- How does IRIS define an "anchor" decision?
- What's the post-observation window (vs baseline)?
- How does IRIS distinguish correlation from impact?

---

## Meta-Control Layer (Filtering & Safety)

These modules prevent inappropriate insights from reaching the LLM.

### Phase 9: Confidence Engine
**Question:** "How reliable is each insight?"

**Files:**
1. `agent/confidence.py` (300+ lines)
   - Entry point: `ConfidenceEngine.compute_confidence(type, entity_id, timestamps)`
   - Learn: sufficiency scoring, consistency, recency decay
   - Weights: 40% sufficiency, 40% consistency, 20% recency

**Time estimate:** 45 min
**Verify understanding:**
- How does IRIS distinguish "high" vs "medium" confidence?
- What's the recency decay curve (30 days)?
- Why does consistency matter?

---

### Phase 10: Conflict Suppression Engine
**Question:** "Which insights logically contradict each other?"

**Files:**
1. `agent/conflict.py` (180+ lines)
   - Entry point: `ConflictSuppressionEngine.suppress(insights)`
   - Learn: incompatibility rules between labels
   - Example: "dissipated" and "reappearing" can't both be true for the same theme

**Time estimate:** 30 min
**Verify understanding:**
- Which pairs of resolution labels are incompatible?
- What does "suppress" mean (silence, merge, or replace)?

---

### Phase 11: Prioritization Engine
**Question:** "Which insights matter most?"

**Files:**
1. `agent/prioritization.py` (300+ lines)
   - Entry point: `InsightPrioritizationEngine.rank_insights(insights)`
   - Learn: multi-factor scoring (confidence, recency, magnitude, novelty, engine weight)
   - Weights: 35% confidence, 20% recency, 20% magnitude, 15% novelty, 10% engine

**Time estimate:** 45 min
**Verify understanding:**
- How does IRIS weight different types of insights?
- What makes an insight "novel"?
- Why does engine matter (tension > leverage > resolution)?

---

## Output Layer (Narrative & LLM)

These modules convert raw insights into natural language.

### Phase 12: Narrative Formatter
**Question:** "How do we describe insights to the user?"

**Files:**
1. `agent/narrative.py` (200+ lines)
   - Entry point: `NarrativeFormatter.format_all(insights)`
   - Learn: template selection, safety validation
   - Key method: `_sanitize_label()` (ensures label matches expected format)
   - Templates per label (e.g., "dissipated" → "appeared frequently in the past but has not appeared recently")

2. `agent/narrative_templates.py`
   - All the natural language templates

**Time estimate:** 30 min
**Verify understanding:**
- Why does IRIS validate labels before formatting?
- What's the narrative contract (no speculation, no causality)?

---

### Phase 13: Intelligence Service (LLM Integration)
**Question:** "How do we talk to Claude/OpenAI/Gemini?"

**Files:**
1. `agent/intelligence.py` (200+ lines)
   - Entry point: `Intelligence.chat(messages, system_prompt, ...)`
   - Learn: multi-model support (OpenAI primary, Gemini fallback)

2. `agent/llm_provider.py` (250+ lines)
   - `LLMProvider` base class and adapters
   - `OpenAIProvider` and `GeminiProvider`

**Time estimate:** 30 min
**Verify understanding:**
- Which LLM is primary, and what's the fallback?
- How does IRIS handle API failures?

---

## Supporting Systems (Reference)

These are utilities that other modules use.

- `agent/evidence.py` — Evidence logging for audit trails
- `agent/explanation.py` — Generating explanations for insights
- `agent/memory.py` — In-session conversation memory
- `agent/preferences.py` — User preferences/settings
- `agent/preferences_guard.py` — Preference validation
- `agent/journal_entry.py` — Journal entry service
- `agent/journal_entry.py` — Journaling interface

---

## Suggested Pace

**Option A: Fast Track (1 week)**
- Day 1: Foundation (database, repos, core)
- Day 2–5: Analytical engines (persistence → leverage)
- Day 6: Meta-control (confidence, conflict, prioritization)
- Day 7: Output (narrative, intelligence)

**Option B: Deep Dive (2–3 weeks)**
- Weeks 1: Foundation (read every line, understand why each table exists)
- Weeks 2: Analytical engines (one per day, run tests, trace data flow)
- Week 3: Meta-control + output (understand decision points)

---

## Verification Checklist

By the end, you should be able to:

- [ ] Draw a data flow diagram: User input → Database → Engines → Gates → Narrative → LLM
- [ ] Explain what each of the 6 analytical engines does in 1 sentence
- [ ] Name 3 gates and explain what they filter
- [ ] Describe the Time windows (recent vs baseline) for at least 2 engines
- [ ] Explain why Confidence is weighted 40/40/20 (sufficiency/consistency/recency)
- [ ] Name 2 invariants from CONTEXT.md and explain why they matter
- [ ] Trace the full path of `companion.chat("hello")` through the system

---

## Resources

- **Domain glossary:** `CONTEXT.md` (all terms, invariants, seams)
- **Architectural decisions:** `docs/adr/` (why certain choices were made)
- **Test examples:** `tests/` (see how modules interact in practice)
- **Entry points:** `iris_api.py`, `companion.py` (how external code uses IRIS)
- **Constants:** `agent/constants.py` (all tuning parameters in one place)

---

## Q&A

**Q: Should I run the code while reading?**
A: Yes! Start with small tests, then run the full pipeline. See how data flows.

**Q: Which module is hardest?**
A: Leverage (requires understanding asymmetry + temporal precedence). Take time with it.

**Q: Can I skip anything?**
A: No. Each module builds on the previous. The order matters.

**Q: What if I get stuck?**
A: Read the tests for that module. They show expected behavior and how to use it.

# Insight Lifecycle Contract

This document defines the strict state machine and gate ordering for the Context Pipeline.
It ensures that raw data is transformed into LLM context safely, transparently, and without "silent mutations."

## 1. The Insight Lifecycle (States)

Every insight (a unit of knowledge derived from raw data) must pass through these states in order.

1.  **Produced** (By Engine)
    *   *Source*: Analytical Engines (Persistence, Trajectory, Tension, etc.)
    *   *Requirement*: Must contain `pattern_type`, `pattern_id`, `score`/`confidence`.
    *   *Status*: Raw data.
    *   *Execution*: Handled via **FastAPI BackgroundTasks** to decouple ingestion from analysis.

2.  **Scored** (By Priority Engine & Confidence Engine)
    *   *Action*: Assigns `confidence_level` and `priority_rank`.
    *   *Requirement*: Evidence weights (Reflections=1.0, Journal=0.9, Habits=0.5) must be applied here.
    *   *Metric Shift*: Supports high-resolution **1-10 scales** for Energy and Mental Clarity.

3.  **Filtered** (Gate 1: Reliability & Preference)
    *   *Action*: Drop insights based on `confidence_threshold` (e.g., "medium") or User Allowlist.
    *   *Outcome*: `DROPPED` or `PASSED`.

4.  **Suppressed** (Gate 2: Conflict Engine)
    *   *Action*: Check for logical contradictions. If A contradicts B, suppress the weaker one.
    *   *Outcome*: `SUPPRESSED` or `VISIBLE`.

5.  **Formatted** (Narrative Layer)
    *   *Action*: Convert structured dict to natural language string.
    *   *Requirement*: Must use approved templates. No "creative writing" by the formatter.
    *   *Mood Invariance*: Mood is inferred from emotional tags, ensuring consistent narrative surfacing.

6.  **Injected** (System Prompt)
    *   *Action*: Final assembly into the prompt string sent to LLM.
    *   *Invariant*: Only `VISIBLE` insights can be injected.

## 2. Gate Ordering (Strict)

The implementation must adhere to this sequence:

1.  **Engine Execution** (Parallel or Serial)
2.  **Preference Gate** (User controls: "Don't show me Tensions")
3.  **Confidence Gate** (System controls: "Don't show low-confidence noise")
4.  **Conflict Gate** (Logic controls: "Don't show contradictions")
5.  **Prioritization Gate** (Budget controls: "Only show top 5")
6.  **Narrative Formatting**
7.  **Final Assembly**

## 3. Invariants

*   **No Silent Drops**: Every dropped insight must have a recorded `drop_reason`.
*   **No Zombie Insights**: An insight marked `SUPPRESSED` must never appear in the Final Assembly.
*   **Traceability**: The final output must be reproducible from the inputs + config.

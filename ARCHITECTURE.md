# IRIS System Architecture

This document details the multi-layer inference pipeline and data flow architecture of the IRIS Companion.

## 1. Data Layer: The "Truth and Lenses" Pattern

IRIS follows a strict decoupling of canonical storage and query-optimized projections.

### 1.1 Canonical Store (PostgreSQL)
*   **Role**: Single Source of Truth.
*   **Data**: User accounts, raw journal entries, chat history, and **canonical embeddings** (`pgvector`).
*   **Integrity**: If all other databases are deleted, the entire system state can be reconstructed from Postgres.

### 1.2 Specialized Lenses
*   **Vector Lens (ChromaDB)**: Optimized for sub-second semantic retrieval and nearest-neighbor lookups.
*   **Graph Lens (Neo4j)**: Optimized for entity-relationship mapping and multi-hop discovery.

---

## 2. The Analytical Pipeline

Data flows through a series of deterministic engines, each answering a specific structural question.

| Engine | Question Answered | Metric Used |
| :--- | :--- | :--- |
| **Persistence** | What keeps appearing? | Semantic Clustering (HDBSCAN/DBSCAN) |
| **Trajectory** | What is changing over time? | Linear Regression (Slope) |
| **Tension** | What co-exists uneasily? | Co-occurrence Asymmetry |
| **Resolution** | What has settled or reappeared? | Temporal Window Deltas |
| **Leverage** | What tends to precede? | Directional Lift (P(B\|A) - P(A\|B)) |
| **Decision Impact**| What tends to follow? | Post-Hoc Sequence Analysis |

---

## 3. Meta-Control Layer (The Gatekeepers)

Before an insight reaches the user, it must pass through the **Meta-Control Spine**. This layer ensures the system remains trustworthy and consistent.

1.  **Confidence & Reliability Engine**: Calculates an evidence-based score (0.0-1.0) using data sufficiency, recency decay, and signal consistency.
2.  **Conflict Suppression Engine**: Detects logical contradictions (e.g., a pattern cannot be both "Dissipated" and "Increasing") and silences the weaker signal.
3.  **Insight Prioritization Engine**: Uses a weighted scorecard to select the top 5 most critical signals, preventing LLM context overload.
4.  **User Control Layer**: Allows the user to tune the "Sensitivity" of the analytical gates (e.g., "Strict Mode" vs. "Exploratory Mode").

---

## 4. Safety & Narrative Firewall

To prevent the LLM from generating harmful advice or assuming causality, IRIS employs a **Narrative Formatter**.

*   **Template-Based**: Facts are rendered into neutral language using strictly mechanical templates.
*   **Regex Guardrail**: A zero-trust validator scans all generated text for forbidden causal/prescriptive verbs (e.g., *caused, should, means, triggered*).
*   **Fail-Closed**: If a narrative violation is detected, the insight is suppressed entirely rather than allowing a risky phrasing to reach the user.

---

## 5. Deployment & Lifecycle

*   **Containerization**: Multi-stage Docker builds separate build-time dependencies (compilers) from the minimal runtime.
*   **Process Management**: Systemd integration ensures IRIS operates as a resilient background service with auto-restart and graceful shutdown (SIGTERM) handling.
*   **Audit Trail**: Every analytical run is logged in an immutable `pattern_evidence` registry for complete historical auditability.

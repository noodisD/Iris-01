# IRIS System Architecture

This document details the multi-layer inference pipeline and data flow architecture of the IRIS Companion.

## 1. Data Layer: The "Truth and Lenses" Pattern

IRIS follows a strict decoupling of canonical storage and query-optimized projections.

### 1.1 Canonical Store (PostgreSQL)
*   **Role**: Single Source of Truth.
*   **Data**: User accounts, raw journal entries, chat history, and **canonical embeddings** (`pgvector`).
*   **Integrity**: If all other databases are deleted, the entire system state can be reconstructed from Postgres.

### 1.2 Specialized Lenses
*   **Graph Lens (Neo4j)**: Optimized for entity-relationship mapping and multi-hop discovery.
*   **Note**: Vector search is now integrated into PostgreSQL via the `pgvector` extension, eliminating external vector database dependencies.

### 1.3 Web Infrastructure
*   **API Layer (FastAPI)**: A multi-user HTTP gateway that orchestrates authentication, companion initialization, and **asynchronous background processing**.
*   **Web Frontend (Vanilla JS)**: A high-performance, single-file interface using modern CSS tokens and Optimistic UI updates for sub-500ms perceived latency.

---

## 2. The Analytical Pipeline

Data flows through a series of deterministic engines, each answering a specific structural question.

### 2.1 Data Enrichment Protocol (Anchoring)
To ensure high-quality semantic clustering, all data is "anchored" before embedding:
*   **Habit Anchor**: Combines Name + Category (Multi-select) + Intent + Metric.
*   **Reflection Anchor**: Combines Mood (Inferred) + Energy (1-10) + Mental Clarity (1-10) + Text.
*   **Effect**: This forces related but different data types (e.g., a "Yoga" habit completion and a "Focused" reflection) into the same semantic neighborhood.

### 2.2 Processing Engines
| Engine | Question Answered | Metric Used |
| :--- | :--- | :--- |
| **Persistence** | What keeps appearing? | Semantic Clustering (WLS Weighted) |
| **Trajectory** | What is changing over time? | Weighted Linear Regression (Slope) |
| **Tension** | What co-exists uneasily? | Co-occurrence Asymmetry |
| **Resolution** | What has settled or reappeared? | Temporal Window Deltas |
| **Leverage** | What tends to precede? | Directional Lift |
| **Decision Impact**| What tends to follow? | Sequence Analysis |

---

## 3. Meta-Control Layer (The Gatekeepers)

Before an insight reaches the user, it must pass through the **Meta-Control Spine**.

1.  **Confidence & Reliability Engine**: Uses **Evidence Tiering** (Reflections=1.0, Journal=0.9, Habit Ticks=0.5) to calculate weighted reliability.
2.  **Conflict Suppression Engine**: Deterministically silences contradictory signals.
3.  **Background Processing**: Heavy computations (LLM Chat, Persistence Engine) are deferred to FastAPI **BackgroundTasks**, keeping the API response cycle < 100ms.
4.  **Proto-Theme Gate**: Clusters with fewer than **5 occurrences** are suppressed as "noise" until they prove persistence.
5.  **Temporal Density Gate**: Only themes with recent activity (>= 3 in last 30 days) are surfaced.
6.  **Insight Prioritization Engine**: Ranks insights by confidence, magnitude, and novelty.

---

## 4. Safety & Narrative Firewall

To prevent the LLM from generating harmful advice or assuming causality, IRIS employs a **Narrative Formatter**.

*   **Template-Based**: Facts are rendered into neutral language using strictly mechanical templates.
*   **Regex Guardrail**: A zero-trust validator scans all generated text for forbidden causal/prescriptive verbs (e.g., *caused, should, means, triggered*).
*   **Fail-Closed**: If a narrative violation is detected, the insight is suppressed entirely rather than allowing a risky phrasing to reach the user.

---

## 5. Deployment & Lifecycle

### Topology: Two-Device Distributed Architecture

The system is designed to split database and application layers:

*   **iris-edge** (192.168.1.24): Database server running PostgreSQL and Neo4j via `docker-compose.yml`
*   **iris-core**: Application server running the FastAPI backend via `Dockerfile.api`
*   **K8s-ready**: Full Kubernetes deployment via Kustomize overlays (`k8s/base/` + `k8s/overlays/dev/` and `k8s/overlays/prod/`)

### Containerization & Deployment

*   **Docker**: Multi-stage builds (`Dockerfile` for local dev, `Dockerfile.api` for iris-core API-only deployment).
*   **Kubernetes**: Kustomize-managed manifests with ConfigMap for non-secrets and encrypted secrets. Image tagging and replicas controlled per environment overlay.
*   **GitOps**: CI/CD updates image tags in `k8s/overlays/prod/` on every build; deployment script on iris-core polls git and applies changes.

### Process Management & Audit

*   **Systemd integration**: IRIS can operate as a resilient background service with auto-restart and graceful shutdown (SIGTERM) handling.
*   **Audit Trail**: Every analytical run is logged in an immutable `pattern_evidence` registry for complete historical auditability.

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for full setup instructions.

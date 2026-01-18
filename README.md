# IRIS Companion v2.1: The Epistemic Mirror

**A local-first, multi-user AI companion built on a deterministic analytical spine.**

IRIS is not a standard "chat-first" assistant. It is a system designed to detect, verify, and prioritize long-term behavioral patterns using a multi-layered data processing pipeline. It operates under a strict **non-interpretive contract**: the system observes and reports evidence but never assumes causality or offers unsolicited advice.

---

## 🧠 Cognitive Architecture

IRIS follows a structured inference pipeline that moves from raw data to prioritized signals:

1.  **Ingestion & Persistence**: Raw journal entries are stored in **PostgreSQL** (Source of Truth). Semantic themes are discovered via **clustering algorithms** (HDBSCAN with DBSCAN fallback).
2.  **Analytical Stack**:
    *   **Trajectory**: Linear regression on theme frequency.
    *   **Tension**: Co-occurrence detection between conflicting patterns.
    *   **Resolution**: Identification of dissipated or reappearing patterns.
    *   **Leverage**: Temporal asymmetry detection (directional influence).
    *   **Decision Impact**: Post-hoc sequence analysis (what follows what).
3.  **Meta-Control Layer**:
    *   **Confidence Engine**: Evidence-based reliability scoring (Sufficiency, Recency, Consistency).
    *   **Conflict Suppression**: Deterministic silencing of logically incompatible insights.
    *   **Prioritization**: Weighted ranking (Confidence, Magnitude, Novelty) to select the most critical 5 signals.
4.  **Narrative Firewall**: A regex-guarded formatter that renders facts into neutral language, blocking causal or prescriptive verbs.

---

## 🛠 Tech Stack

*   **Runtime**: Python 3.11 (optimized slim multi-stage Docker build)
*   **Primary DB**: PostgreSQL + `pgvector` (Canonical Store)
*   **Graph DB**: Neo4j (Relationship Lens)
*   **Vector DB**: ChromaDB (Semantic Retrieval Lens)
*   **ML**: Scikit-learn, HDBSCAN
*   **Validation**: Pydantic Settings

---

## 🚀 Quick Start

### 1. Configure Environment
```bash
cp .env.example .env
# Fill in your OPENAI_API_KEY and secure passwords
```

### 2. Deploy via Docker
```bash
docker-compose up --build -d
```

### 3. Launch CLI
```bash
python companion.py
```

---

## ⌨️ Command Registry

### **Core Commands**
*   `/journal` - Create a new journal entry.
*   `/themes` - View recurring themes.
*   `/discover` - Manually trigger semantic theme discovery.

### **Diagnostic & Meta-Control**
*   `/priority` - View the current leaderboard of ranked insights.
*   `/why <type> <id>` - Audit why an insight was surfaced (Score/Confidence breakdown).
*   `/hidden` - View insights suppressed in the last run (Conflict/Confidence).
*   `/explain <type> <id>` - View the raw evidence backing an observation.
*   `/confidence <type> <id>` - Inspect the reliability metrics for a pattern.

### **Management**
*   `/settings` - View/Change analytical gates (Confidence floor, max items, engine allowlist).
*   `/rebuild-vector` - Reconstruct the ChromaDB lens from PostgreSQL.
*   `/rebuild-graph` - Reconstruct the Neo4j lens from PostgreSQL.

---

## 🛡 Safety & Epistemic Integrity

IRIS is designed to be a "Mirror," not a "Coach." 
*   **Zero-Trust Phrasing**: The system is physically blocked from using words like "caused," "should," or "means."
*   **Evidence-Only**: Every chat response is grounded in specific, timestamped database records.
*   **User Sovereignty**: Users control the sensitivity of the analytical gates through the `/settings` layer.

---

**IRIS: Seeing patterns before they become narratives.**
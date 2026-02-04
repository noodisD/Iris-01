# IRIS: The Epistemic Mirror

**A local-first, multi-user AI companion built on a deterministic analytical spine and a high-performance Vanilla JS interface.**

IRIS is not a standard "chat-first" assistant. It is a sophisticated system designed to detect, verify, and prioritize long-term behavioral patterns. It operates under a strict **non-interpretive contract**: the system observes and reports evidence but never assumes causality or offers unsolicited advice.

---

## 🧠 Cognitive Architecture

IRIS follows a structured inference pipeline that moves from raw data to prioritized signals:

1.  **Ingestion & Anchoring**: Every input (habit completion, reflection, message) is semantically "anchored" with context before being stored in **PostgreSQL**.
2.  **Asynchronous Analysis**: Heavy analytical tasks (embeddings, graph linking) run in **background tasks**, ensuring sub-500ms UI responsiveness.
3.  **Analytical Stack**:
    *   **Persistence**: Clustering related thoughts into proven Themes (Threshold: 5).
    *   **Trajectory**: Linear regression on theme frequency with **Evidence Tiering**.
    *   **Tension**: Co-occurrence detection between conflicting patterns.
    *   **Temporal Density**: Only surfacing themes active in the last 30 days.
4.  **Meta-Control Layer**:
    *   **Confidence Engine**: Weighted reliability scoring (Reflections > Habit Ticks).
    *   **Conflict Suppression**: Deterministic silencing of logically incompatible insights.
    *   **Prioritization**: Selecting the top 5 most critical signals for the LLM context.

---

## 🛠 Tech Stack

*   **Frontend**: Vanilla JavaScript + CSS Design Tokens (Optimized for Speed & Zero Dependencies)
*   **Backend**: FastAPI + Uvicorn (Multi-user HTTP Gateway with Background Tasks)
*   **Primary DB**: PostgreSQL + `pgvector` (Canonical Store + Vector Search)
*   **Graph DB**: Neo4j (Relationship Lens)
*   **Containerization**: Docker + Kubernetes (Kustomize overlays for dev/prod)

---

## 🚀 Quick Start

### 1. Configure Environment
```bash
cp .env.example .env
# Fill in your OPENAI_API_KEY and secure passwords
```

### 2. Deploy via Docker (Local All-in-One)
Runs PostgreSQL, Neo4j, and the API on one machine.
```bash
docker compose up --build -d
```
Access the app at **http://localhost:8000**

### 3. Local Development
```bash
# Terminal: Backend (serves frontend automatically)
.venv/bin/python iris_api.py
```

---

## 🏗 Deployment Topologies

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for full guides. Three supported setups:

| Mode | What runs where | How to start |
|:---|:---|:---|
| **Local dev** | Everything on one machine | `docker compose up --build -d` |
| **Distributed** | DBs on `iris-edge`, API on `iris-core` | `docker compose -f docker-compose.iris-core.yml up -d` on iris-core |
| **Kubernetes** | API pods in a K8s cluster, DBs external | `kubectl apply -k k8s/overlays/prod/`

---

## ⌨️ Features & Interface

### **Habits & Consistency**
Track your daily routines with multi-select categories and duration/count logging. IRIS uses **Relative Consistency** math to ensure new habits show 100% progress if completed every day since creation.

### **Reflections & Mental Clarity**
Capture your state using high-resolution **1-10 scales** for Energy and Mental Clarity. Select multiple emotions to have IRIS automatically infer your general mood.

### **Analytical Chat**
Chat with IRIS to explore your patterns. IRIS uses the **Epistemic Framework** to differentiate between your current input and computed historical facts. Press **Enter** to send.
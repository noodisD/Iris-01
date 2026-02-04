# IRIS Deployment Guide

This document covers deploying IRIS across three topologies: local development, distributed (multi-device), and Kubernetes.

---

## Architecture Overview

IRIS uses a **distributed architecture** that separates databases from the API:

```
┌──────────────────────────┐         ┌──────────────────────────┐
│     iris-edge (DB)       │         │    iris-core (API)       │
│  - PostgreSQL + pgvector │ ◄─────► │  - FastAPI Uvicorn       │
│  - Neo4j                 │  TCP/IP │  - Serves frontend       │
└──────────────────────────┘         └──────────────────────────┘
     192.168.1.24                         192.168.1.X (or K8s)
```

---

## 1. Local Development (All-in-One)

Everything runs on one machine via Docker Compose.

### Setup

```bash
cd /home/iris/Iris-01

# Copy .env template
cp .env.example .env

# Edit .env with your API keys
nano .env
```

### Deploy

```bash
# Build and start (first time)
docker compose up --build -d

# Or on subsequent runs
docker compose up -d

# Check status
docker compose ps
```

### Access

- **Frontend**: http://localhost:8000
- **API**: http://localhost:8000 (same)
- **PostgreSQL**: localhost:5433 (from outside container)
- **Neo4j**: localhost:7688 (from outside container)

### Logs

```bash
# API logs
docker compose logs -f agent

# Database logs
docker compose logs -f postgres
docker compose logs -f neo4j
```

### Stop

```bash
docker compose down
```

---

## 2. Distributed Deployment (iris-edge + iris-core)

Databases run on **iris-edge** (192.168.1.24), API runs on **iris-core**.

### Prerequisites

- **iris-edge**: Docker installed, accessible at 192.168.1.24
- **iris-core**: Docker installed, network access to iris-edge:5432 and 7687

### Step 1: Start Databases on iris-edge

On the iris-edge machine:

```bash
ssh iris-edge

cd /path/to/Iris-01

# Start only PostgreSQL + Neo4j (no API)
docker compose up postgres neo4j -d

# Verify running
docker compose ps
```

This binds PostgreSQL on `:5432` (inside container) and Neo4j on `:7687`, exposed to the network.

### Step 2: Start API on iris-core

On the iris-core machine:

```bash
cd /path/to/Iris-01

# Configure .env to point to iris-edge
cat > .env << EOF
POSTGRES_DB=iris_db
POSTGRES_USER=iris_user
POSTGRES_PASSWORD=your-secure-password
POSTGRES_HOST=192.168.1.24
POSTGRES_PORT=5433

NEO4J_USER=neo4j
NEO4J_PASSWORD=your-secure-password
NEO4J_URI=bolt://192.168.1.24:7688

OPENAI_API_KEY=sk-your-key
ENV=prod
LOG_LEVEL=INFO
EOF

# Start only the API
docker compose -f docker-compose.iris-core.yml up --build -d

# Verify running
docker compose -f docker-compose.iris-core.yml ps
```

The API listens on port 8000 on iris-core.

### Step 3: Test Connectivity

```bash
# From iris-core, test database connection
docker compose -f docker-compose.iris-core.yml logs iris_api | grep -i "connected"

# Or curl the health endpoint
curl http://localhost:8000/health
```

### Access

- **Frontend**: http://iris-core-ip:8000
- **API**: http://iris-core-ip:8000
- **Databases**: Only accessible from iris-core (by design)

### Update & Redeploy

To pull latest code and rebuild on iris-core:

```bash
cd /path/to/Iris-01
git pull origin main
docker compose -f docker-compose.iris-core.yml up --build -d
```

Or use the automated script:

```bash
bash scripts/deploy-iris-core.sh
```

---

## 3. Kubernetes Deployment

Deploy to a local K8s cluster (k3s, Minikube, or on-prem) with Kustomize.

### Prerequisites

- `kubectl` configured to your cluster
- `kustomize` (built into `kubectl apply -k`)
- Databases (PostgreSQL, Neo4j) accessible from K8s cluster
- Secrets encrypted (see `docs/SECRETS_MANAGEMENT.md` after implementation)

### Step 1: Prepare Databases

Databases must be accessible from the K8s cluster network. Options:

**Option A:** Docker containers on a node reachable by K8s

```bash
# On a node with network access to the cluster
docker compose up postgres neo4j -d
```

**Option B:** Kubernetes StatefulSets (advanced)

Add PostgreSQL and Neo4j Helm charts or raw K8s manifests to the `k8s/` directory.

### Step 2: Configure K8s Manifests

Edit `k8s/base/configmap.yml` to point to your database server:

```yaml
data:
  POSTGRES_HOST: <your-db-server-ip>
  POSTGRES_PORT: "5432"
  NEO4J_URI: bolt://<your-db-server-ip>:7687
```

### Step 3: Deploy

**Development environment:**

```bash
kubectl apply -k k8s/overlays/dev/
```

**Production environment:**

```bash
kubectl apply -k k8s/overlays/prod/
```

### Step 4: Verify Deployment

```bash
# Check pods
kubectl get pods -n iris

# Check services
kubectl get svc -n iris

# View logs
kubectl logs -n iris -l app=iris-api -f

# Port-forward to test locally
kubectl port-forward -n iris svc/iris-service 8000:8000

# Access at http://localhost:8000
```

### Update Image Tag

To deploy a specific image version:

```bash
kubectl set image deployment/iris-api -n iris \
  iris-api=noodis/iris-core:v0.1.0 \
  --record
```

### GitOps-Style Updates (Automated)

The CI/CD pipeline updates `k8s/overlays/prod/patches/deployment.yaml` with new image tags on every build. To pull this automatically:

```bash
# On the K8s control node
git -C /path/to/Iris-01 pull origin main
kubectl apply -k k8s/overlays/prod/
```

Or set up a polling script (see `scripts/deploy.sh` for reference).

### Access the Application

**Port-forward (development):**

```bash
kubectl port-forward -n iris svc/iris-service 8000:8000
# Access at http://localhost:8000
```

**Ingress (production):**

An Ingress is defined in `k8s/base/ingress.yml` for host-based routing:

```bash
# Add to /etc/hosts on client machines
iris.local <cluster-node-ip>

# Access at http://iris.local
```

### Rollback

To revert to a previous image:

```bash
kubectl rollout undo deployment/iris-api -n iris
kubectl rollout status deployment/iris-api -n iris --watch
```

### Delete Deployment

```bash
kubectl delete -k k8s/overlays/prod/
```

---

## Environment Variables Reference

### For All Topologies

| Variable | Example | Required |
|:---|:---|:---|
| `POSTGRES_DB` | `iris_db` | Yes |
| `POSTGRES_USER` | `iris_user` | Yes |
| `POSTGRES_PASSWORD` | `secure_password` | Yes |
| `POSTGRES_HOST` | `localhost` or `192.168.1.24` | Yes |
| `POSTGRES_PORT` | `5433` (docker-compose) or `5432` (direct) | Yes |
| `NEO4J_USER` | `neo4j` | Yes |
| `NEO4J_PASSWORD` | `secure_password` | Yes |
| `NEO4J_URI` | `bolt://localhost:7688` | Yes |
| `OPENAI_API_KEY` | `sk-proj-...` | Yes |
| `ENV` | `dev` or `prod` | No (default: dev) |
| `LOG_LEVEL` | `INFO` or `DEBUG` | No (default: INFO) |

### Docker Compose Port Mapping

- PostgreSQL: 5433 (host) → 5432 (container)
- Neo4j: 7688 (host) → 7687 (container)
- API: 8000 (both)

When connecting from inside a container, use the **container port** (5432, 7687). When connecting from the host, use the **host port** (5433, 7688).

---

## Troubleshooting

### Database Connection Refused

**Local dev:**
```bash
docker compose ps  # Check if postgres/neo4j are running
docker compose logs postgres  # Check for startup errors
```

**Distributed:**
```bash
# From iris-core, test connectivity to iris-edge
nc -zv 192.168.1.24 5432
nc -zv 192.168.1.24 7687
```

**Kubernetes:**
```bash
# Get node IP where postgres is running
kubectl get nodes -o wide

# Check if service is reachable from pod
kubectl exec -it -n iris <pod-name> -- \
  nc -zv <postgres-service-or-ip> 5432
```

### API Not Starting

```bash
# Local dev
docker compose logs agent

# Distributed
docker compose -f docker-compose.iris-core.yml logs iris_api

# Kubernetes
kubectl logs -n iris deployment/iris-api
```

Look for `POSTGRES_PASSWORD` or `NEO4J_PASSWORD` errors — verify `.env` is correctly set.

### Slow Database Queries

See `docs/PGVECTOR_MIGRATION.md` "Troubleshooting" section for query optimization.

---

## Next Steps

- **Secrets management**: See `docs/SECRETS_MANAGEMENT.md` (when implemented)
- **CI/CD pipeline**: See `.github/workflows/ci.yml`
- **Architecture details**: See `ARCHITECTURE.md`

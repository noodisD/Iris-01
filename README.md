# IRIS

A personal analytical companion. You write — journal entries, reflections, habit
ticks — and IRIS looks for patterns that persist, drift, conflict or fade, then
reports what it observed. It runs entirely on your machine, against your own
database.

It is deliberately **not** a chat-first assistant. It operates under a
non-interpretive contract: report the evidence, never assert causality, never
give unsolicited advice. A pattern that appeared 12 times and then stopped is
reported as exactly that.

---

## What it is, concretely

One Python process and one PostgreSQL database. That's the whole system.

```
┌────────────────────────────────────────────────┐
│  uvicorn iris_api:app   (127.0.0.1:8000)       │
│    ├── /api/*        the HTTP API              │
│    └── /             the built React SPA       │
└───────────────────────┬────────────────────────┘
                        │
              PostgreSQL 18 + pgvector
       (entries, embeddings, themes, insights)
```

- **Single user, loopback only.** No accounts, no login, no authentication. It
  binds to `127.0.0.1` and must not be exposed to a network.
- **One datastore.** pgvector is a PostgreSQL extension, so 1536-dimension
  embeddings live in ordinary rows next to everything else and a similarity
  search is a normal SQL query with a `WHERE user_id = …` on it.
- **OpenAI** for chat (`gpt-5.5`, set with `OPENAI_MODEL`) and embeddings
  (`text-embedding-3-small`). The chat model is a one-line change; the embedding
  model is not — the vector column is fixed at 1536 dimensions and the IVFFlat
  indexes are built for it, so changing it means a migration and re-embedding
  everything.
  Nothing else leaves the machine.

## Requirements

- Python 3.11 (`.python-version`), managed with [uv](https://docs.astral.sh/uv/)
- PostgreSQL 18 with pgvector
- Node 20+ for the frontend build
- An OpenAI API key

## Setup

**1. PostgreSQL with pgvector.** The stock database recipes use the plain
`postgres` image, which has no pgvector — IRIS cannot create its schema without
it. Use the pgvector image instead:

```bash
sudo docker run -d --restart unless-stopped \
  -p 127.0.0.1:5432:5432 \
  -v iris_pgdata:/var/lib/postgresql \
  --name postgres18 \
  -e POSTGRES_HOST_AUTH_METHOD=trust \
  -e POSTGRES_USER=iris_user -e POSTGRES_DB=iris_db \
  pgvector/pgvector:pg18
```

Mount `/var/lib/postgresql`, **not** `/var/lib/postgresql/data`: PostgreSQL 18
moved `PGDATA` to a version-specific subdirectory, and the old path looks
correct while silently persisting nothing. If your container already exists,
`scripts/setup_db.sh` creates the role and database inside it.

**2. Configure and install.**

```bash
cp .env.example .env      # add OPENAI_API_KEY; check POSTGRES_* match the above
uv sync
```

**3. Build the frontend** (the API serves it from the same process):

```bash
cd frontend && npm install && npm run build && cd ..
```

**4. Run.**

```bash
uv run uvicorn iris_api:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Schema migrations run at startup; the single local
user is created on first request.

For frontend work, `cd frontend && npm run dev` serves on :5173 and proxies
`/api` to :8000, so requests stay same-origin.

## How the analysis works

Every entry is embedded and stored. From there:

1. **Persistence** — entries are matched to existing themes by cosine
   similarity (≥ 0.70); when nothing matches, clustering looks for a new theme.
   A cluster needs **5** occurrences before it counts as a theme rather than
   noise.
2. **Trajectory** — weighted regression over occurrence frequency: rising,
   falling, emerging, fading, stable.
3. **Tension** — themes that co-occur while trending in opposite directions.
4. **Resolution** — dissipated, stabilised, persisting, reappearing.
5. **Leverage / Decision impact** — what tends to precede and follow what.

Findings then pass the **meta-control layer**, in this order: engine enablement
→ confidence threshold → conflict suppression → prioritisation → budget. Only
then are they rendered into language, by templates, through a regex firewall
that rejects causal and prescriptive wording (`caused`, `should`, `because`,
`means`…). A finding that cannot be phrased neutrally is dropped rather than
softened.

**Conversation is not evidence.** Chat messages are embedded so IRIS can recall
them, but they never create or reinforce themes — otherwise mentioning a pattern
would manufacture proof of it. Skipped habits are not evidence either.

## Development

```bash
uv run pytest                  # offline, deterministic, no API spend
uv run ruff check .
cd frontend && npm run lint    # tsc --noEmit
```

The suite stubs OpenAI at the SDK boundary and runs against a separate
`iris_test_db`, which it refuses to touch unless the database name contains
"test". `IRIS_TEST_LIVE_OPENAI=1` opts into the real API for the tests that
assert on live model output.

## Deployment

One machine, one service: see `scripts/iris.service.example`. There is no
container image and no orchestration — a personal single-user app does not need
either, and the previous Docker path had been broken and unused for months.

### Schema changes

The schema is owned by `migrations/NNNN_*.sql`, applied in numeric order at
startup and recorded in `schema_migrations` with a checksum. To change it, add a
migration — editing one that has already run is refused, because databases that
already applied it would keep the old definition.

`tests/test_schema_snapshot.py` compares the live schema against a committed
snapshot, so any change also lands as a reviewable diff; regenerate it with
`python -m tests.test_schema_snapshot --update`.

### What IRIS is allowed to say

Settings carries the analytical gates: the confidence a finding needs before it
is raised, how many can reach one conversation, and which of the six engines
run. They are the same preferences the CLI's `/settings` writes.

## Deliberately not built

- **Authentication and multi-user.** Removed on purpose; this is a local app.
- **Wearables / biometrics.** There is no device integration. The UI previously
  displayed invented HRV and sleep figures; that screen is gone rather than
  faked.
- **Data connectors** (calendar, Spotify, photos…). Listed in Settings as not
  yet built; nothing reads them.

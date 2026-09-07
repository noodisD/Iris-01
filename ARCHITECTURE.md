# IRIS Architecture

How the system is built, as it actually stands. For domain vocabulary and
invariants see `CONTEXT.md`; for the insight lifecycle contract see
`docs/context_pipeline_contract.md`.

## 1. Shape

One process, one datastore.

```
uvicorn iris_api:app          serves /api/* and the built SPA, loopback only
  └── agent/                  the analytical package
        └── PostgreSQL 18 + pgvector
```

There is no separate vector database and no graph database. Both existed once:
ChromaDB/FAISS was replaced by pgvector in January 2026, and Neo4j was removed
in September 2026 after it turned out to be write-only — every call into it was
an insert, nothing in the product ever read from it, and because its driver
connected at import time an outage took the whole API down.

### Storage

PostgreSQL is the only store. Because pgvector is an extension rather than a
service, an embedding is a column on an ordinary row:

- `embeddings` — one canonical vector per source, `UNIQUE(source_type, source_id, model_name)`
- `themes` — a relational row carrying `centroid_embedding`
- `theme_occurrences` — theme ↔ source, `ON DELETE CASCADE`
- plus the per-engine caches (`theme_trajectories`, `theme_tensions`,
  `pattern_resolutions`, `pattern_leverage`, `decision_impacts`,
  `pattern_confidence`, `pattern_evidence`, `insight_priorities`)

This is what lets a similarity search carry a relational constraint: nearest
neighbours *and* `WHERE user_id = …` in one statement, one transaction. A
standalone vector store cannot express the user-scoping invariant without
duplicating ownership metadata and keeping it in sync.

Both IVFFlat indexes are created with the schema. Note that an IVFFlat index
built on an empty table has degenerate centroids; rebuild it once real data
exists.

## 2. Ingestion

Writing is separated from analysing. A write stores the row, enqueues it in
`processing_queue`, and returns; a background worker (`agent/work_queue.py`,
started by the API's lifespan and by the CLI) does the rest. So an embedding
provider outage delays the work rather than losing it — the queue row survives
the outage and the process, and retries on a widening backoff.

`agent/pipeline.py: run_processing_pipeline(source_type, source_id)` is what the
worker runs:

1. Mark the row `processing`.
2. Read **that row** back by id. (It used to read back any row in that status,
   so one entry's text could be embedded under another's id.)
3. Embed it (`text-embedding-3-small`, 1536 dimensions), store the vector.
4. Match against existing themes; when nothing matches, run clustering to see
   whether a new theme has formed.
5. Mark the row `complete`.

**What counts as evidence** is a deliberate boundary. Journal entries,
reflections and completed habits do. Chat messages are embedded for recall but
never become occurrences — otherwise talking about a pattern would create proof
of it, and a dissipated theme would revive itself inside the very request that
reported on it. Skipped habits are excluded for the same reason in reverse: a
skip is evidence the pattern did *not* occur, but the embedded text is dominated
by the habit's own name, so counting it made abandoning a habit look like
practising it.

## 3. Engines

| Engine | Question | Method |
| :-- | :-- | :-- |
| Persistence | What keeps appearing? | Cosine matching (≥0.70) + DBSCAN clustering |
| Trajectory | What is changing? | Weighted regression on frequency |
| Tension | What co-exists uneasily? | Co-occurrence with divergent trends |
| Resolution | What settled or came back? | Recent vs baseline window deltas |
| Leverage | What tends to precede? | Directional lift |
| Decision impact | What tends to follow? | Sequence analysis |

Thresholds live in `agent/constants.py` and are documented in `CONTEXT.md`;
a cluster needs 5 occurrences before it is a theme rather than a proto-theme.
Clustering uses HDBSCAN when installed and falls back to scikit-learn DBSCAN,
which is the configuration in practice.

## 4. Meta-control

Findings pass through gates in this order, which `CONTEXT.md` and the pipeline
contract both specify:

**enablement → confidence → conflict suppression → prioritisation → budget**

The budget slice is last for a reason: it truncates to `max_items`, so applying
it before ranking discarded insights in engine-registration order and the
highest-weighted engine could never reach the ranker.

- **Confidence** weights evidence by source (reflection 1.0, journal 0.9, habit
  with notes 0.8, bare tick 0.5) and scores sufficiency, consistency and recency
  at 40/40/20.
- **Conflict suppression** silences logically incompatible pairs.
- **Prioritisation** ranks by confidence, recency, magnitude, novelty and engine
  weight, then the budget keeps the top *k* (default 5).

Every suppression is recorded with a reason, so what was hidden is auditable.

## 5. Narrative firewall

Insights are rendered by fixed templates in `agent/narrative_templates.py` — one
per engine, with no free-text slots. Rendered output is then matched against a
forbidden lexicon (`caused`, `should`, `means`, `implies`, `because`, `due to`,
`triggered`…). A violation drops the insight rather than rephrasing it.

## 6. Failure behaviour

- **PostgreSQL unreachable** — the pool is built lazily, so the process still
  starts; `/health` round-trips a `SELECT` and returns 503 `degraded`.
- **OpenAI unreachable** — embedding uses bounded retry with exponential backoff
  on transient errors only. Beyond that the pipeline raises, and the ingest
  queue keeps the item and retries it later, so an entry written during an
  outage becomes evidence once the outage clears. After the backoff schedule is
  exhausted the item stays queued with its last error rather than being dropped.
  Chat failures raise; they are never written into the conversation as Iris's
  reply.
- **Clustering or an engine fails** — logged and skipped; ingestion still
  commits, because the entry itself is the thing that must not be lost.

## 7. Lifecycle

Run under systemd on one machine (`scripts/iris.service.example`), bound to
loopback. The schema is created idempotently on first connection. There are no
migrations: schema changes are `CREATE TABLE IF NOT EXISTS` plus additive
`ALTER TABLE … ADD COLUMN IF NOT EXISTS`, which cannot express a constraint
change — a real migration tool is the outstanding piece of work here.

# Architecture decision records

Why the constraints in this codebase exist. Read one before proposing a change
that contradicts it — the point of these is that settled decisions are not
re-litigated by accident, only deliberately.

| ADR | Decision | Load-bearing for |
|---|---|---|
| [0001](ADR-0001-single-user-loopback.md) | Single user, bound to loopback, no auth | Every security question; why CORS is absent |
| [0002](ADR-0002-one-datastore.md) | PostgreSQL + pgvector is the only store | Why user-scoping is enforceable in one query |
| [0003](ADR-0003-what-counts-as-evidence.md) | Only deliberate logging counts as evidence | Why chat and skips never become occurrences |
| [0004](ADR-0004-deployment.md) | One systemd service, not a container image | Why there is no Dockerfile |
| [0005](ADR-0005-caching.md) | Cache only where there is a reader, always with expiry | Resolution's TTL; trajectory having none |
| [0006](ADR-0006-time.md) | UTC instants for analysis, local days for habits | Why `DTZ` findings in the trackers are correct |
| [0007](ADR-0007-one-admission-policy.md) | Chat and Insights answer with one policy | Why `InsightsService` routes through the gates |
| [0008](ADR-0008-schema-ownership.md) | `create_schema()` owns the schema; a snapshot catches drift | Why there is no alembic yet |
| [0009](ADR-0009-analytical-measures.md) | Measures must mean what they are named | The bounds every engine's arithmetic must hold |
| [0010](ADR-0010-one-journal-store.md) | A journal entry is a reflection | Why the CLI writes through ReflectionService |
| [0011](ADR-0011-durable-ingest-queue.md) | Writing is separated from analysing | Why analysis is eventually consistent |

New ADRs use [ADR-0000-TEMPLATE.md](ADR-0000-TEMPLATE.md) and the naming rules
in [`docs/agents/domain.md`](../agents/domain.md).

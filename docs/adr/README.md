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
| [0008](ADR-0008-schema-ownership.md) | ~~`create_schema()` owns the schema~~ *(superseded by 0012)* | Why alembic was rejected |
| [0009](ADR-0009-analytical-measures.md) | Measures must mean what they are named | The bounds every engine's arithmetic must hold |
| [0010](ADR-0010-one-journal-store.md) | A journal entry is a reflection | Why the CLI writes through ReflectionService |
| [0011](ADR-0011-durable-ingest-queue.md) | Writing is separated from analysing | Why analysis is eventually consistent |
| [0012](ADR-0012-migrations.md) | Migrations own the schema | How to change a constraint |
| [0013](ADR-0013-importing.md) | Imported entries are reflections, dated when they happened | Why an import must be reviewed before it lands |
| [0014](ADR-0014-themes-in-what-differs.md) | Themes are found in what differs between entries | Why comparison is mean-centred and linkage is complete |
| [0015](ADR-0015-reading-entries.md) | Reading entries, with every quote verified | Why a finding without verbatim quotes is dropped |
| [0016](ADR-0016-stored-candidates.md) | What reading finds is a proposal until confirmed | Why candidates exist and nothing measures them |
| [0017](ADR-0017-sensor-sources.md) | Sensor sources enter through one seam, as evidence | Why sensor data never forms its own themes |
| [0018](ADR-0018-mobile-lan-api.md) | LAN-only API surface for a paired Android app | Why the LAN bind defaults to OFF and the bearer gates it |
| [0019](ADR-0019-phone-app-over-lan.md) | Paired phone accesses the full API over pinned TLS | Why web and pairing remain loopback-only |
| [0020](ADR-0020-chat-opens-a-new-session.md) | Each chat open starts an empty session | Why web and phone chat do not render the stored transcript |
| [0021](ADR-0021-ideas-framework.md) | Ideas are confirmed propositions, not measured themes | Why arguments are not occurrences and critiques are not evidence |
| [0022](ADR-0022-reach-iris-over-tailscale.md) | IRIS is reachable away from home over the owner's Tailscale network | Why only the owner's tailnet login gets in, and why Funnel is never used |

New ADRs use [ADR-0000-TEMPLATE.md](ADR-0000-TEMPLATE.md) and the naming rules
in [`docs/agents/domain.md`](../agents/domain.md).

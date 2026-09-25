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
┌──────────────────────────────────────────────────────┐
│  scripts/serve_iris.py                                │
│    ├── 127.0.0.1:8000   local API and React SPA       │
│    └── LAN_IP:8765      pinned TLS paired Android API │
│        (only when LAN_BIND_HOST is explicitly set)    │
└─────────────────────────┬────────────────────────────┘
                        │
              PostgreSQL 18 + pgvector
       (entries, embeddings, themes, insights)
```

- **Single local user.** No accounts or login. The web UI binds only to
  `127.0.0.1`; never expose that unauthenticated listener publicly. An
  explicitly configured private-LAN TLS socket admits the paired Android app
  to `/api/` with its bearer, except laptop-only pairing routes. The native
  phone UI requires fingerprint or the device screen lock on opening and
  after five minutes in the background (ADR-0019).
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
uv run python scripts/serve_iris.py
```

Open http://127.0.0.1:8000. Schema migrations run at startup; the single local
user is created on first request.

**The supported deployment is this source checkout.** The wheel
(`uv build`) carries the application but not `migrations/` or the built
frontend, so an installed copy cannot create or upgrade its own schema — and
now says so instead of reporting that it has no migrations to run.

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
would manufacture proof of it. Skipped habits are not evidence either. Opening
Chat on the web or phone starts an empty session. Earlier messages stay stored
and analysed; they are not shown as the current transcript.

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

### Bringing in what you have already written

The Import page reads an export — Notion, Obsidian, Day One, a folder of notes,
a zip — and voice recordings, and turns them into entries dated when they were
written. It shows you what it found before anything is saved, and refuses to
commit an entry whose date it could not determine: a guessed date is counted in
the wrong week for good. On Android, Journal can record a voice entry and opens
Import for transcript and date review before it becomes a journal entry.
Recordings are transcribed and the audio is kept, so you can listen back and
so a better model can re-read them later.

### Collect live phone readings

Set `LAN_BIND_HOST` to the laptop's private Wi-Fi IPv4 address in `.env`, then
restart `uv run python scripts/serve_iris.py`. With this setting absent the
launcher remains loopback-only. It never binds `0.0.0.0`; keep port 8765 off
public networks. If the LAN listener fails, the loopback web UI keeps serving
and Settings reports the failure. Allow inbound TCP 8765 only from home Wi-Fi.

Build and install the Android collector with
`cd android && ./gradlew :app:installDebug` after ADB recognizes the Pixel
(JDK 17, Android SDK 36).
In laptop **Settings → Android live sensors**, generate a token, then scan
its pairing QR in the phone app. The phone pins the persistent server public
key and sends only over Wi-Fi on the laptop's subnet. When the laptop IP changes,
restart IRIS and scan the address-only QR without rotating the token. Grant
location, physical activity, notifications and Usage access; Health Connect
adds heart rate, sleep and SpO2 from any app whose records IRIS is permitted
to read, with background read where offered. A Fitbit later contributes
through Health Connect when its app writes records there. The foreground
service collects observed step increments and permitted Health Connect
readings, retries queued JSON after Wi-Fi returns and wakes for sync during
Doze. A reboot or app update requires a tap to resume collection.

The Sensors page groups new deliveries into one pending batch per source and
review day. Linking a source type to an active theme admits the latest approved
reading per source, theme and UTC day; unlinked data stays inert. If readings
arrive after opening a batch, confirmation asks for another review. Deleting a
confirmed batch retracts its evidence and restores an older approved daily
reading if present. Disconnect from laptop Settings to revoke the phone token.

### What IRIS is allowed to say

Settings carries the analytical gates: the confidence a finding needs before it
is raised, how many can reach one conversation, and which of the six engines
run. They are the same preferences the CLI's `/settings` writes.

## Deliberately not built

- **Authentication and multi-user.** Removed on purpose; this is a local app.
- **Direct watch/Bluetooth sync.** Health readings come from permitted Health
  Connect records, including Fitbit if its app syncs there; IRIS never claims
  an unobserved HRV measurement.
- **Data connectors** (calendar, Spotify, photos…). Listed in Settings as not
  yet built; nothing reads them.

# IRIS

A personal companion whose primary purpose is to help you grow on your own terms.
IRIS draws on your journal entries, reflections, habits, conversations and
approved records to help you understand yourself, explore your assumptions, and
notice supported patterns as they appear during conversation.

Personal factual claims must be grounded in available records. Interpretations
are explicitly labeled hypotheses, open to correction. IRIS uses reflective
listening, Socratic questioning and other psychotherapy-informed techniques,
without presenting itself as a therapist or diagnosing you. It can challenge a
choice respectfully and offer an optional next step tied to your own goals.

IRIS reads what you give it: journal entries (typed, dictated or imported),
recorded therapy sessions, your answers to a baseline questionnaire, and chat
conversations you choose to add. From that it finds **patterns**, recurring
context–response dynamics backed by verbatim quotes and checked against their
sources; tentative **insights** with supporting and contrary accounts; and your
**ideas**, positions linked into a graph. Chat draws on all of it, with an exact
memory search over your writing and sessions. Only what you save, import or
add is sent to be read; staged imports, sessions and drafts wait for your
click, and runs over the archive show their cost first. IRIS keeps itself in
check with a health report (`python -m agent.doctor`).

In a session, a questionnaire answer or an added chat, only your own turns are
evidence: the therapist's, the question's and IRIS's words are context. A
chat is evidence only if you add it. Patterns and insights are observations,
not causes or diagnoses. See [ARCHITECTURE.md](ARCHITECTURE.md) for how it is
built, [CONTEXT.md](CONTEXT.md) for the domain rules, and
[docs/reference-evaluation.md](docs/reference-evaluation.md) for how pattern
quality was evaluated.

---

## What it is, concretely

One Python process and one PostgreSQL database. That's the whole system.

```
┌──────────────────────────────────────────────────────┐
│  scripts/serve_iris.py                                │
│    ├── 127.0.0.1:8000   local API and React SPA       │
│    ├── 127.0.0.1:8001   tailnet door (tailscale serve)│
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
  to `/api/` with its bearer, except laptop-only pairing, named-place and
  Timeline-import routes. The native phone UI requires fingerprint or the device
  screen lock on opening and after five minutes in the background (ADR-0019).
- **One datastore.** pgvector is a PostgreSQL extension, so 1536-dimension
  embeddings live in ordinary rows next to everything else and a similarity
  search is a normal SQL query with a `WHERE user_id = …` on it.
- **OpenAI** for chat (`OPENAI_MODEL`, default `gpt-5.5`), source-checked
  reading and pattern synthesis (`OPENAI_WORKER_MODEL`, on the Flex tier),
  embeddings (`text-embedding-3-small`), voice notes and speaker separation.
  A session recording's words are written locally by Whisper when
  `WHISPER_PYTHON` points at an environment with faster-whisper (ADR-0030). A change of chat/worker model affects provider
  output and can invalidate a checked reading; the embedding model also fixes
  the vector column at 1536 dimensions and changing it requires migration and
  re-embedding. Eligible journal passages are sent to the configured worker
  provider during reading, not during the provider-free cost preflight.

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

Every entry is queued in the same transaction it is saved in, then embedded. A
long entry is also cut into passages, so chat finds the part that matters, and a
dictated one gets a punctuated reading copy with exactly the same words.

1. **Reading.** Each entry is read once per version into accounts: events,
   self-reports, intentions and what-ifs, with the situation, the response and,
   when you said them, the feeling, reason and outcome. Every field is quoted
   word for word from your text and kept only if an independent check finds the
   quote supports it. Long sessions are read 25 turns at a time.
2. **Patterns.** When every entry is read, one synthesis run finds recurring
   context–response dynamics across the archive, groups retellings of the same
   event, and keeps exceptions visible. You can confirm or correct each one.
   A full rebuild takes an hour or more on the Flex tier.
3. **Insights.** Tentative claims over a chosen range, each with supporting,
   contrary and unknown accounts. Twenty-four optional process lenses may
   annotate a pattern; they never classify you.
4. **Ideas.** On request, your positions are read out with dated quotes and
   linked: supports, contradicts, refines, depends on, same meaning, applies.

The older analytical engines (persistence, trajectory, tension, resolution,
leverage, decision impact, lifelong) still run over themes for chat's
"observed patterns" and the weekly letter. Their findings pass one admission
policy (coverage → enablement → confidence → conflict suppression → ranking)
and fixed templates behind a firewall that rejects causal and prescriptive
wording (`caused`, `should`, `because`…).

**Conversation is evidence only when you add it.** Chat messages are embedded
so IRIS can recall them; "Add to IRIS" under the chat box makes a conversation
evidence, your turns only (ADR-0032). The chat reopens the conversation you
last wrote in after a reload, and lists earlier ones to continue (ADR-0033).

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
snapshot, so any change also lands as a reviewable diff; regenerate it against
the test database with `POSTGRES_DB=<test db> python -m tests.test_schema_snapshot --update`
(opening the live database applies pending migrations to it).

Back up first: `uv run python scripts/backup_db.py <label>` writes a dump to
`data/backups/` without the Observatory's telemetry, a few tens of megabytes.

### Keeping it healthy

`uv run python -m agent.doctor` checks what errors never show: whether jobs and
the pattern update are moving, whether every quote is still found word for word,
whether memory search finds what an exact search finds, whether chat's context
is complete, and more. It stores each run and leads with what changed since the
last; every check names a runbook in `docs/runbooks/`. It also lists what waits
on you (phone batches, reviews, drafts) and warns when model spend passes
`WEEKLY_BUDGET_USD` (default $0.50 a week). Install the daily run with the two
`scripts/iris-doctor.*.example` units; IRIS then shows the latest result in a
banner. Before restarting, run
`uv run python -m agent.doctor --can-restart`: a restart during a pattern update
throws away its progress.

### Bringing in what you have already written

The Import page reads an export — Notion, Obsidian, Day One, a folder of notes,
a zip — and voice recordings, and turns them into entries dated when they were
written. It shows you what it found before anything is saved, and refuses to
commit an entry whose date it could not determine: a guessed date is counted in
the wrong week for good. On Android, Journal can record a voice entry and opens
Import for transcript and date review before it becomes a journal entry.
Recordings are transcribed and the audio is kept, so you can listen back and
so a better model can re-read them later.

### Therapy sessions

Import → Therapy sessions takes a transcript with `**[HH:MM:SS] Name:**` turns,
or a recording alone. A recording is written down locally by Whisper, its
speakers told apart from the recording and your stored voice samples, and
mis-heard words checked against that second hearing; every change is listed.
You say which speaker is you, check the day and time, and click Import (cost
shown first). Only your turns are ever quoted as yours (ADR-0028, ADR-0030).

### Baseline questionnaire

The Questionnaire screen holds the intake questionnaire you were given,
shown in English with the Polish on request. Its text stays in a local file in
`data/`, never in this repository. Answer by typing or in a short interview with
IRIS ("Next unanswered question", "Say more with IRIS" for short answers), or
start from suggestions made only of your own sentences. Answers are drafts
until you add a section; chat can then see and discuss them (ADR-0029).

### Write a day

Journal on web and Android uses one Markdown writing pane with headings, bold,
italics, lists, checkboxes and quotes, plus a five-part check-in (energy, mood,
sleep quality, stress and focus). A check-in without words is saved but not
embedded. Older plain-text entries stay plain; formatted entries are shown as
Markdown while analysis and quotes use their readable words.


### Collect live phone readings

Set `LAN_BIND_HOST` to the laptop's private Wi-Fi IPv4 address in `.env`, then
restart `uv run python scripts/serve_iris.py`. With this setting absent the
launcher remains loopback-only. It never binds `0.0.0.0`; keep port 8765 off
public networks. If the LAN listener fails, the loopback web UI keeps serving
and Settings reports the failure. Allow inbound TCP 8765 only from home Wi-Fi.

To use the phone away from home, set `LAN_BIND_HOST` to the laptop's Tailscale
address instead, allow TCP 8765 on the `tailscale0` interface only, and scan the
address QR once. The phone then reaches IRIS over Tailscale on any network.

### Use the web UI away from home

Set `TAILNET_OWNERS` to your Tailscale login, restart IRIS, then run
`tailscale serve --bg http://127.0.0.1:8001` (enable MagicDNS and HTTPS in the
Tailscale admin console first). IRIS is then at `https://<laptop>.<tailnet>.ts.net`
on your own devices; any other login is refused, and pairing stays on the laptop.
Never use Tailscale Funnel, which would publish IRIS to the Internet. See
[ADR-0022](docs/adr/ADR-0022-reach-iris-over-tailscale.md).

Build and install the Android collector with
`cd android && ./gradlew :app:installDebug` after ADB recognizes the Pixel
(JDK 17, Android SDK 36).
In laptop **Settings → Android live sensors**, generate a token, then scan
its pairing QR in the phone app. The phone pins the persistent server public
key and sends only over Wi-Fi on the laptop's subnet, or over Tailscale
when the laptop's address is a Tailscale one. When the laptop IP changes,
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

On the laptop, Sensors also accepts the JSON export from Google Maps Timeline
(Maps → profile → Settings → Location & privacy → Timeline → Export). The upload
stages dated visits and trips; confirm a single batch or a date range before
they count. Name home and office from confirmed HOME/WORK suggestions or enter
coordinates yourself, then inspect the Days table. Location coverage below
50% leaves the day kind unknown; only step counts known to cover a full day
are eligible for comparisons. App categories can be overridden per package.
Named place coordinates and suggestions are available only on the laptop, not
through the phone or tailnet door. No day measurement becomes journal text.
Days use the laptop's local time zone and a 06:00–24:00 window; sleep counts on
the wake day. Repeated cumulative step readings use the largest daily total,
and overlapping sleep reports are not added twice.

After upgrading an existing installation, rebuild older UTC-based day rows
once after migrations apply:
`uv run python -c 'from agent.database import db; from agent.days.recompute import recompute; recompute(db.local_user_id())'`.

### Compare measured days

Insights → Days compared compares the five check-in scores with confirmed phone
and Timeline day measurements: office/home days, or days above and below your
own median commute, full-day steps, screen time, social/video/game share or
sleep. Ties at the median are excluded; location-based comparisons require at
least 50% coverage. Each side needs at least five days, a check-in mean gap of
at least one point and a two-sided 2,000-shuffle permutation p-value ≤ 0.01.
Each sentence shows both day counts. These are differences, **not causes**.
Choose “rings true”, “doesn’t ring true” or “unsure” for each. Only currently
qualifying comparisons marked “rings true” can enter chat when you ask; a
saved verdict remains even if a comparison temporarily disappears. No journal
prose or coordinates enter a comparison.

### What IRIS is allowed to say

Settings carries the analytical gates: the confidence a finding needs before it
is raised, how many can reach one conversation, and which of the older engines
run (seven can be switched). They are the same preferences the CLI's
`/settings` writes.

## Deliberately not built

- **Authentication and multi-user.** Removed on purpose; this is a local app.
- **Direct watch/Bluetooth sync.** Health readings come from permitted Health
  Connect records, including Fitbit if its app syncs there; IRIS never claims
  an unobserved HRV measurement.
- **Data connectors** (calendar, Spotify, photos…). Listed in Settings as not
  yet built; nothing reads them.

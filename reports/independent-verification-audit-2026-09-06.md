# IRIS — Packed Independent Verification Findings

**Date:** 2026-09-06  
**Snapshot:** `recovery/2026-09-06-baseline` @ `14a4b242ae908c36b6a9ecf72ed9f1e5b39bfac3`  
**Working tree at audit:** clean  
**Mode:** diagnostic only; no remediation in this document

This file packs **all findings** from the three reviews into one document:

| Part | Source | Role |
| --- | --- | --- |
| 1 | Coordinator consolidated report | Verdict, matrix, roadmap |
| 2 | Auditor A complete report (R1) | Bottom-up implementation audit, 45 findings |
| 3 | Auditor B complete report (R2) | Adversarial consistency audit, 42 findings |
| 4 | Original review finding catalog (R0) | Ground-zero review index vs later remediations |

Original R0 prose: `~/.claude/plans/graceful-roaming-adleman.md`

---



# Part 1 — Consolidated report

# IRIS Independent Verification Audit — Consolidated Report

**Coordinator:** lead verification (this session)  
**Date:** 2026-09-06  
**Snapshot:** `recovery/2026-09-06-baseline` @ `14a4b242ae908c36b6a9ecf72ed9f1e5b39bfac3`  
**Working tree:** clean (start and end)  
**Mode:** diagnostic only — no remediation was performed

Independent reports:
- **R0** original ground-zero review: `/home/noodis/.claude/plans/graceful-roaming-adleman.md` (also copied to `/tmp/iris-audit-2026-09-06/original-review-r0.md`)
- **R1** Auditor A (bottom-up implementation): `/tmp/iris-audit-2026-09-06/auditor-a-report.md`
- **R2** Auditor B (adversarial consistency): `/tmp/iris-audit-2026-09-06/auditor-b-report.md`

---

## 1. Executive verdict

**Current condition.** IRIS is a local-first personal “epistemic mirror” in the middle of a 2026-09-06 recovery. The analytical spine is real. The product identity in *code* is a single-user FastAPI process plus a React SPA plus PostgreSQL/pgvector. The product identity in *README/ARCHITECTURE/Dockerfile* is still a multi-user Vanilla JS + Chroma/FAISS + Poetry + Docker compose stack. Those two stories cannot both be true.

**Can it build, run, test, and deploy?**

| Capability | Verdict | Evidence |
|---|---|---|
| Python dependency resolution | **Yes** | `uv.lock` present; Auditor A `uv lock --check` resolved 72 packages; `.venv` is Python 3.11.9 |
| Backend import / compile | **Yes** | `compileall` pass; `import iris_api` → `COMPANION_AVAILABLE=True`, **53** route objects, no CORS, no JWT |
| Local API process | **Can start, with caveats** | `__main__` binds `127.0.0.1:8000`; Postgres 18.6 on `localhost:5432` is up; `iris_db` exists (1 user `local`, 0 journals/reflections/habits/themes, 2 messages + 2 embeddings). `/health` does not probe the database. Live chat/review were **not** exercised (paid OpenAI). |
| Frontend typecheck | **Yes** | `npx tsc --noEmit` exit 0 |
| Frontend production build | **Unverified** | `npm run build` would write `frontend/dist/`; not run. An untracked dist already exists. |
| Tests | **Partial, environment-dependent** | Dedicated `iris_test_db` exists and refuses non-`test` names. HEAD claims “134 passed”. Independent runs: **132 passed, 1 failed**, but **not the same failure**. Coordinator reproduction: health-invariant **fails** with a dummy OpenAI key (`assert 0 == 1`); isolated `test_complete_journal_entry_flow` **passes** on a currently empty journal table. Docker/image build **blocked**. |
| Container deploy | **No** | `Dockerfile` copies missing `poetry.lock` and deleted `iris_frontend.html`; binds `0.0.0.0`; docker.sock permission denied on this host |
| Documented `docker-compose up` | **No** | Compose Postgres is pg16 on host **5433**; this host uses native PG **18.6** on **5432**. Agent image cannot build. |
| systemd | **No** | `scripts/iris.service.example` points at `/home/noodis/Myself/apps/personal_ai_agent_minimal` and starts `companion.py` |

**Most serious confirmed problems**

1. **Ingest identity bug** — `run_processing_pipeline` marks *this* `source_id` processing, then fetches *any* row with that status (`LIMIT 1`, no id, no user). Wrong text can be embedded under the caller’s id. (`agent/pipeline.py:77–87`, `agent/database.py:764–780`)
2. **HTTP path cannot form new themes** — `discover_themes()` is only called from the CLI (`companion.py:176–181,830`) and tests. `check_persistence()` returns `None` when the user has no themes (`agent/persistence.py:126–128`). A SPA-only user never gets insights.
3. **Documented deploy path is fiction** — README recommends `docker-compose up --build`; Dockerfile needs files that do not exist.
4. **Silent failure** — pipeline/embedding errors are printed/logged and swallowed; HTTP still 200; many API tests stay green.
5. **Body UI fabricates physiology** while the only real endpoint is `GET /api/body/source` → `{kind:"none"}`. `frontend/.env.local` has `VITE_USE_MOCKS=true`.
6. **If the broken Docker path were used**, the API has **no auth** and the image binds **0.0.0.0**. Local `__main__` is loopback-only, which is the intended single-user mode.

**Overall confidence in this assessment: high** for architecture, contracts, deploy artifacts, and the ingest/discovery defects (direct code + coordinator reproduction). **Medium** for live chat quality, IVFFlat recall, and race-condition magnitude (not load-tested). **Low** for “134/134 tests pass with a live key” — that claim was not reproduced, and the suite is not isolated enough to treat a green run as proof.

**Do not start remediation until this report is approved.**

---

## 2. Audit methodology

### Repository snapshot used

| Field | Value |
|---|---|
| Repo | `/home/noodis/Iris-01` |
| Branch | `recovery/2026-09-06-baseline` |
| Commit | `14a4b242ae908c36b6a9ecf72ed9f1e5b39bfac3` |
| Subject | `fix: stop counting chat messages as theme occurrences` |
| Working tree | clean |
| Host date | 2026-09-06 |
| Host `python3` | 3.14.7 |
| `.python-version` / `.venv` | 3.11.9 |
| uv | 0.12.9 |
| Docker CLI | 29.7.2; daemon socket **permission denied** |
| Postgres | 18.6 on `localhost:5432`; pgvector 0.8.6; DBs `iris_db`, `iris_test_db` (plus unrelated `iris_rails_*`) |
| Node | v26.8.1 / npm 11.19.0 |

R0 was **not** taken on this same commit. Original R0 diagnosis targeted `main` @ `ce30b11` plus a large uncommitted 2026-06-14 tree. The same R0 document then records owner decisions and remediations through `14a4b24`. R1/R2 audited the post-remediation snapshot. Cross-checks treat R0 claims as hypotheses about *current* code, not as historical trivia.

### How independence was maintained

- Two subagents, **separate conversation contexts**, launched in parallel.
- **Same** branch/commit/environment (shared worktree). Worktree isolation was **not** used: a fresh worktree would omit `.venv`, `frontend/node_modules`, and `.env`, which would force package installs forbidden by the safety rules.
- Original review path (`~/.claude/plans/graceful-roaming-adleman.md`) was **withheld**. Both prompts forbade reading Claude/Codex/Grok session histories and each other’s reports.
- Auditor A was not given Auditor B’s findings, and vice versa, until both files existed.
- Coordinator read R0 before launch (required for later reconciliation) but did not inject R0 claims into auditor prompts.

**Independence limitation (disclosed):** both auditors ran pytest against the **same** `iris_test_db` around the same time. That likely contributed to them observing **different** single test failures. Coordinator re-ran the two disputed tests **sequentially** afterward.

### Commands and evidence sources (coordinator adjudication)

- Read R1 and R2 in full; catalogued R0.
- Re-read `agent/pipeline.py`, `agent/database.py` (`get_items_to_process`, `get_unassigned_embeddings`, `hash_password`, `update_preference`, schema FKs), `agent/core.py`, `agent/persistence.py`, `agent/journal_entry.py`, `agent/trackers/reflections.py`, `agent/trackers/habits.py`, `iris_api.py` (auth seam, journal mapping, health, stream, Dockerfile bind), `Dockerfile`, `docker-compose.yml`, `CONTEXT.md` gate order, frontend `body.ts` and `.env.local`, `scripts/setup_db.sh`, `scripts/iris.service.example`.
- Grep: `discover_themes` (CLI + tests only), `CORSMiddleware` / `token: str` (absent), `neo4j` / `python-jose` (absent from tree and venv).
- Import `iris_api`: 53 route objects; only body route is `/api/body/source`.
- Pytest (dummy `OPENAI_API_KEY`, `IRIS_TEST_POSTGRES_DB=iris_test_db`):
  - `test_system_health_invariant` → **FAIL** `assert 0 == 1` (User B, 5 reflections, 0 patterns)
  - `test_complete_journal_entry_flow` isolated → **PASS** (0 leftover `journal_entries` at that moment)
- Read-only counts on `iris_db` and `iris_test_db` (no message bodies read).
- `docker ps` → permission denied.
- Working tree remained clean.

### Important limitations

- No browser click-through; no `npm run build`; no `docker build`; no live OpenAI chat.
- No `uv lock` / `uv sync` / package installs (R0 previously showed `uv lock --check` can auto-download CPython).
- Application `iris_db` was not written by this coordinator pass except via the earlier auditors’ API import (lazy pool; lifespan `create_schema` not started as a server).
- `iris_test_db` **was** written by auditors’ and coordinator’s pytest. Leftovers remain (14+ users, 45 reflections, 41 embeddings at one count).
- GitHub Issues unread (`gh` not authenticated).
- Secret values from `.env` were not copied into reports.

---

## 3. Verified current-state map

### Purpose and users

**Intended (code + `CONTEXT.md` + commit `9d97803`):** one person on one machine. Ingest journal-like text, reflections, and habits; cluster **themes**; run deterministic engines (persistence / trajectory / tension / resolution / leverage / decision-impact); gate and narrate; inject into an LLM chat that is supposed not to invent causality.

**Still advertised (`README.md`, `ARCHITECTURE.md`, `pyproject.toml` description):** multi-user HTTP gateway, Vanilla JS, ChromaDB/FAISS, Docker as the recommended path.

### Architecture (as implemented)

```
Vite SPA (frontend/src, React 18 + TS)
  dev :5173  --proxy /api-->  FastAPI iris_api.py  (127.0.0.1:8000)
  prod: FastAPI serves frontend/dist if present
           |
           |  get_current_user_id() → users.username=IRIS_DEFAULT_USER ("local")
           |  no JWT, no CORS, no cookies
           v
  HabitTracker / ReflectionService / InsightsService / PersonalAICompanion
           |
           |  run_processing_pipeline()  → OpenAI embeddings (text-embedding-3-small)
           |  AnalysisPipeline: engines + enablement/confidence/budget
           |  then conflict + rank + second max_items slice
           |  NarrativeFormatter → Intelligence (OpenAI; Gemini SDK present but unused)
           v
  PostgreSQL 18 + pgvector   (canonical store; no Neo4j, no Chroma, no FAISS)
```

Second entry point: CLI `companion.py` (`iris` script) still presents Login / Create User against the same `users` table.

### Components

| Component | Path | Status |
|---|---|---|
| HTTP API | `iris_api.py` | Active; 53 route objects; single-user seam |
| SPA | `frontend/` | Active; several screens stubbed or mock-gated |
| Design prototype | `frontend/design-prototype/` | Reference only |
| Archived UI | `archive/iris-frontend-react/` | Inert; docs still say Vanilla JS is current |
| CLI | `companion.py` | Active but degraded (NameError journal, `\1` logs, dead `/rebuild-vector`, multi-user login) |
| Data layer | `agent/database.py` | Singleton lazy pool; `CREATE TABLE IF NOT EXISTS` is the only “migration” |
| Engines | `agent/{persistence,trajectory,tension,resolution,leverage,decision_impact}.py` | Active; do not use unused `engine_base.py` |
| Narrative firewall | `agent/narrative*.py` | Active on template strings only; unused `narrative_system.py` |
| Insights adapter | `agent/insights_service.py` | Maps leverage/decision-impact to `kind: "causal"` |
| Tests | `tests/` | 134 collected; live OpenAI test in default collection |
| CI | none | no `.github/` |
| Containers | `Dockerfile`, `docker-compose.yml` | Stale / non-buildable |

### Data flow (primary UI workflow)

1. SPA `POST /api/journal` → **reflections** (not `journal_entries`), mood stored as `energy_level`.
2. `ReflectionService.create_reflection` calls `run_processing_pipeline('reflection', id)` synchronously; errors `print()`’d.
3. Pipeline embeds fetched row content (possibly the **wrong** row) and `check_persistence()` against **existing** themes only.
4. Insights/chat require themes. New themes are created only by `PersistenceEngine.discover_themes()`, which the API never calls.
5. Chat: new `PersonalAICompanion` per request; `conversation_id` in the URL is ignored; SSE is word-chunking of a completed reply.

### Integrations

- **OpenAI** embeddings + chat (required for the product loop). Default model names disagree (`gpt-4.1-mini` vs `settings.OPENAI_MODEL=gpt-4o-mini`).
- **Gemini** optional via EOL `google-generativeai==0.8.6`; companion never sets `use_gemini=True`.
- **Connectors catalog** is UI state in `user_app_settings`; no OAuth.
- **Body/wearables:** honest stub `/api/body/source`; SPA overview routes do not exist.

### Deployment model (intended vs files)

Owner decision recorded in R0: systemd + uvicorn on loopback + Postgres on the box. Files on disk still include a Poetry Dockerfile, compose of postgres+agent, and a systemd unit for another path. Native Postgres 18.6 is what this host actually runs.

---

## 4. Three-review verification matrix

Statuses: **Confirmed** / **Partially confirmed** / **Plausible but unverified** / **Contradicted by evidence** / **Outdated finding** / **False positive** / **Requires owner clarification**.

Confidence is evidence quality, not vote count.

| Finding | R0 | R1 | R2 | Primary evidence | Final status | Confidence |
|---|---|---|---|---|---|---|
| Pipeline fetches any `processing`/`pending` row, not `source_id` | LI-4 / R1 **open** | A-R-02 Critical | B-LI-02 Critical | `pipeline.py:77–87`; `database.py:779–780` `WHERE processing_status = %s LIMIT %s` — no id. Test `test_complete_journal_entry_flow` asserts on unscoped `limit=1`. | **Confirmed** | High |
| HTTP ingest never discovers new themes | not listed as such | noted in component map; not Critical | B-LI-01 / B-R-03 Critical | `discover_themes` only in `companion.py` + tests; `check_persistence` returns `None` if no themes | **Confirmed** (missed as a named R0 finding) | High |
| Dockerfile copies missing `poetry.lock` + `iris_frontend.html` | OD-3; M1.3 not started | A-OD-02 Critical | B-OD-01 Critical | `Dockerfile:16–26`; `git ls-files` has neither file | **Confirmed** | High |
| README/ARCHITECTURE describe Vanilla JS + Chroma + multi-user | OD-4/5, LI-2 | A-OD-01 High | B-OD-02 High | `README.md:1–32`; `ARCHITECTURE.md:15–19`; code is React + pgvector + single-user | **Confirmed** | High |
| Unauthenticated API; Docker `0.0.0.0` | R2/R3 claimed **closed** as JWT; residual bind | A-R-01 Critical | B-R-01 Critical | No `token`/`CORSMiddleware`; `get_current_user_id`; Dockerfile CMD `--host 0.0.0.0`; `__main__` is `127.0.0.1` | **Partially confirmed** — JWT gone; exposure remains **if** compose/image used | High |
| Two auth models / JWT / default SECRET_KEY / python-jose | LI-1, R3 | not present | not present | `python-jose` not importable; no `/api/auth`; no `token: str` | **Outdated finding** (fixed in `9d97803`) | High |
| Neo4j import-time hard dependency | LI-7 claimed closed `c591509` | leftovers only (env/pyc) | leftovers only | no `neo4j` package; no `graph_db.py`; compose has no Neo4j service | **Outdated finding** (removed) | High |
| CORS `*` + credentials | LI-25 claimed closed | no CORS | no CORS | coordinator: `has cors False` | **Outdated finding** | High |
| Tests run against the **application** DB | LI-23 / R4 claimed closed `b4bdcec` | A-R-07 (test DB leftover + paid API) | B-R-04 | `conftest.py:11,78–84` forces `iris_test_db` and refuses names without `test` | **Outdated finding** for app-DB mutation; **Confirmed** leftover isolation holes | High |
| Chat messages counted as theme occurrences | LI-34 claimed fixed `14a4b24` | A-LI-02 High (discovery hole) | B-LI-04 High | `pipeline.py:133` skips messages for `check_persistence`; `get_unassigned_embeddings` still includes `message` | **Partially confirmed** — online match fixed; discovery not | High |
| Dual journal: UI→reflections, CLI/`journal_entries` | LI-16 | A-LI-01 High | B-LI-03 High | `iris_api.py:630–680`; `core.py` loads both stores | **Confirmed** | High |
| `JournalEntry.create_entry` NameError `journals` | not in original R0 list | A-LI-07 High | B-LI-09 High | `journal_entry.py:13,61` | **Confirmed** (missed by original R0) | High |
| Budget gate before conflict/rank | LI-3 / R9 **open** | A-LI-03 High | B-LI-07 Medium | `core.py:114–116,181–209`; `budget_gate` docstring “Assumes insights are already ranked” | **Confirmed** | High |
| Double pipeline on `POST /api/reflections` | LI-5 **open** | A-LI-16 Medium | B-LI-16 Medium | `reflections.py:76–80` + `iris_api.py:563–565`. SPA journal path does **not** double-fire. | **Confirmed** (legacy reflections API) | High |
| Body overview routes missing; mocks fabricate biometrics | LI-9, LI-10 | A-LI-05 High | B-LI-05 High | `body.ts` calls `/body/overview`; API only `/api/body/source`; `.env.local` `VITE_USE_MOCKS=true` | **Confirmed** | High |
| `VITE_USE_MOCKS` comment claims insights/review/settings mocked | LI-11 | A-LI-05 / component map | B-OD-06 | `.env.local:8–11` vs only `body.ts` checks `useMocks()` | **Confirmed** | High |
| Connectors / forget / export are theater | connectors in R0 as static catalog | A-LI-11, A-LI-19 | B-LI-06 High | `iris_api.py:697–708`; Settings buttons no `onClick` | **Confirmed** | High |
| Swallowed pipeline errors; tests green without embeddings | LI-24 (later R0 softened) | A-R-03 High | B-R-03 / B-LI-19 | `reflections.py:77–80` `print`; coordinator dummy-key health-invariant fail; API tests still pass under dummy key per A | **Confirmed** | High |
| LLM errors persisted as assistant text | related LI-24 | A-R-03 | B-LI-19 High | `intelligence.py:177–179`; `core.py:158–159` | **Confirmed** | High |
| SHA-256 unsalted passwords | R3 (auth crypto) — JWT closed, hash remains | A-OD-05 High | B-R-01 | `database.py:24–26` | **Confirmed** (residual) | High |
| setup_db.sh / systemd wrong names and paths | OD-11, OD-12 | A-OD-04 High | B-OD-04 High | `iris_app`/`iris_agent`; WorkingDirectory `.../personal_ai_agent_minimal` | **Confirmed** | High |
| `google-generativeai` EOL | OD-6 | A-OD-03 Medium | B-OD-03 High | lock 0.8.6; GitHub archived 2025-12-16; support ended 2025-11-30 (verified 2026-09-06) | **Confirmed** | High |
| Python 3.11.9 pin vs black/mypy 3.14 | OD-1 | A-OD-07 Medium | B-OD-05 Medium | `.python-version`; `pyproject.toml` tool config | **Confirmed** | High |
| Naive vs aware datetimes | LI-14 | A-R-10 Medium | B-R-08 Medium | HEAD commit queues M3.3; `datetime.now()` vs TIMESTAMPTZ | **Confirmed** | High |
| Two preference systems; UI cannot set gates | LI-17 | A-LI-13 Medium | B-LI-20 Medium | `_PREF_KEY_MAP` vs `user_preferences` | **Confirmed** | High |
| `NARRATIVE_FAIL_MODE` env ignored | LI-18 | A-LI-09 Low | B-LI-11 Medium | `narrative_policy.py:11` hardcoded `"raise"` | **Confirmed** | High |
| Model default split 4.1-mini vs 4o-mini | OD-9 | A-LI-06 Medium | B-LI-12 Medium | `core.py:49` vs `config.py:25` vs `persistence.py` | **Confirmed** | High |
| Onboarding API unused by UI | not emphasized | A-LI-10 Medium | B-LI-10 Medium | `OnboardingScreen.tsx` `nav('/chat')` | **Confirmed** | High |
| Pool `maxconn=5` + nested checkouts | LI-32 | A-R-11 Medium | B-R-05 High | `database.py:55–56` | **Confirmed** (exhaustion not load-tested) | Medium |
| `/health` always OK | LI-8 (later: import used to crash; lazy pool `9e9ac89`) | implied | B-R-09 Medium | `iris_api.py:190–193` no DB ping; import now succeeds | **Partially confirmed** — process can start; health still blind | High |
| No migration framework; missing CASCADE / embedding FKs | R27, LI-23 comments | A-R-04/05 High | B-R-06 High | `create_schema()`; `conftest.py:90–97` | **Confirmed** | High |
| IVFFlat `lists=100` on empty tables | not in R0 | A-R-06 Medium | B-R-06 | `database.py:196–201`; `iris_db` has 2 embeddings | **Confirmed** (recall impact inferred) | Medium |
| No CI | R26 | A-R-09 Medium | B-OD-09 Medium | no `.github/` | **Confirmed** | High |
| Dead `engine_base.py` / `narrative_system.py` | LI-19 | A-LI-15 Low | B component map | zero production importers | **Confirmed** (graph_sync_queue **removed**) | High |
| CLI `\1` log strings | LI-21 | A-R-13 Low | B-LI-09 | `companion.py` `logger.error(f"\1: {e}")` | **Confirmed** | High |
| Dead identical import guard | LI-22 | not restated | not restated | `core.py:40–43` both branches identical | **Confirmed** (coordinator) | High |
| pydantic `.dict()` | OD-13 | A-OD-06 Low | B-OD-08 Low | `iris_api.py:455,612` | **Confirmed** | High |
| `docs/adr/` missing | OD-14 | A-OD-09 Low | B-OD-10 Low | `ls docs/adr` fails | **Confirmed** | High |
| Habit color not persisted | LI-9 | A-LI-12 Low | B-LI-14 | no color column; `_habit_to_contract` | **Confirmed** | High |
| Fake SSE (full reply then split words) | LI-6 adjacent | A-LI-17 Medium | B-R-05 | `iris_api.py:290–317` | **Confirmed** | High |
| `hdbscan` imported conceptually, not installed | not in R0 | A-V-17 / A-LI-15 | B-LI-09 (warning filter) | `import hdbscan` ModuleNotFoundError; sklearn DBSCAN fallback | **Confirmed** | High |
| Hatch wheel omits `iris_api.py` / `companion.py` | not in R0 | not listed | B-OD-09 Medium | `pyproject.toml` `packages = ["agent"]`; entrypoints at repo root | **Confirmed** | High |
| `conversation_id` ignored | LI-9 adjacent (`inferred=[]`) | not listed | B-LI-15 Medium | `iris_api.py:262–275` loads all history | **Confirmed** | High |
| Habit **skips** run persistence as completions | not in R0 | unknown #9 | B-LI-14 Medium | `habits.py:101–106`; allow-list includes `habit_completion` | **Confirmed** | High |
| Reflections mutable / hard-delete orphans embeddings | CONTEXT invariant vs code | not listed | B-LI-13 Medium | `PUT/DELETE /api/reflections`; CONTEXT “sources immutable” | **Confirmed** | High |
| Mood stored as energy; review sleepHours=0 | LI-15 | A-LI-01 related | B-LI-17 Medium | `iris_api.py:637–638,985` | **Confirmed** | High |
| Suggestion accept 204 no-op | LI-9 | A-R-12 Low | B-LI-06 | `iris_api.py:926–930` | **Confirmed** | High |
| SQL identifier interpolation in `update_preference` | LI-31 | not restated | not restated | `database.py:1963,1968` `f"SELECT {key}"` | **Confirmed** (coordinator; no HTTP writer for analytical keys) | High |
| `httpx` undeclared direct dep | LI-28 | not restated | not restated | `pyproject.toml` has no `httpx`; present in `uv.lock` transitively | **Confirmed** | Medium |
| Compose Neo4j healthcheck password mismatch | LI-29 | n/a | n/a | Neo4j service removed from compose | **Outdated finding** | High |
| Stale CLI duplicate `q` | LI-20 | gone | gone | recovery diff deleted `q` | **Outdated finding** | High |
| Uncommitted SPA / insights_service | R8 | n/a | n/a | committed in `70bf1d2` | **Outdated finding** | High |
| Four June resolution-cache tests failing | R12 claimed fixed `14a4b24` | different failure | different failure | current failures are health-invariant (no embeddings) and/or dirty unscoped fetch — **not** those four names | **Outdated finding** as stated; suite is **not** cleanly green | High |
| HEAD “134 passed, 0 failed” | R0 §15 | contradicted (132/1 dummy key) | contradicted (132/1 dirty DB) | coordinator: health-invariant fails without live embeddings | **Contradicted by evidence** as a current fact | High |
| Git remote `gh:` alias missing (OD-22) | R0 execution | not reported | not reported | `git remote -v` → `git@github.com:noodisD/Iris-01.git` | **Outdated finding** (URL rewritten) | High |
| “User not in docker group” as drift | R0 then self-corrected (Omarchy policy) | A-V-16 permission denied | docker not used | `docker ps` permission denied; policy vs bug is **owner/OS** | **Requires owner clarification** (access method), not a code defect | High |
| New-DB bootstrap circular `CREATE EXTENSION` | LI-33 claimed fixed `b4bdcec` | schema exists | schema exists | not re-run on a brand-new empty cluster | **Plausible but unverified** now (fix claimed; not re-broken in this pass) | Medium |
| Live OpenAI key should be rotated | R5 | key present (length only) | key present | `.env` gitignored; not in git history per R0 | **Requires owner clarification** | Medium |
| `origin/dev` K8s assets | OD-17; owner retired | not inspected here | not inspected | local `origin/dev` not re-fetched (`gh` unauthenticated) | **Requires owner clarification** | Low |

---

## 5. Confirmed outdated elements

These are outdated because they **break or mislead**, not because a newer version exists.

1. **Dockerfile / Poetry / Vanilla HTML** — `Dockerfile:16–26` (`poetry.lock`, `iris_frontend.html`). Recommended deploy cannot build.
2. **README / ARCHITECTURE / pyproject description** — multi-user, Vanilla JS, ChromaDB/FAISS, Docker-first. Code is single-user React + pgvector.
3. **`COMPATIBILITY_REPORT.md`** — Poetry + pypika/onnxruntime/Chroma; those deps are gone.
4. **`scripts/setup_db.sh`** — creates `iris_app` / `iris_agent` on 5432; app uses `iris_user` / `iris_db`.
5. **`scripts/iris.service.example`** — nonexistent path; starts CLI not API.
6. **`.env.example` / compose ports** — 5433 vs live 5432; Chroma telemetry flag; frontend example `VITE_BACKEND_URL=http://localhost:8080` vs API **8000**.
7. **`google-generativeai` 0.8.6** — support ended 2025-11-30 (verified 2026-09-06).
8. **Tooling Python 3.14 vs runtime 3.11.9**.
9. **Pydantic v1 `.dict()`** on v2 models.
10. **Archive README** still points at deleted `iris_frontend.html`.
11. **`docs/PGVECTOR_MIGRATION.md`** Flask/psycopg3 topology.
12. **Unsalted SHA-256** as a password hash (leftover CLI users table).
13. **Compose image `pgvector/pgvector:pg16`** vs host PostgreSQL **18.6**.
14. **Live `.env` still has `NEO4J_*` keys** for a deleted component.

Vite 5 / React 18 being behind current majors is **not** treated as a confirmed operational defect (both still run; optional Phase 5).

---

## 6. Confirmed logical inconsistencies

1. **Product identity:** single-user loopback API vs multi-user README vs multi-user CLI login on one `users` table.
2. **Journal split-brain:** SPA writes `reflections`; engines/tests/CLI/`_get_recent_journal_entries_context` still think `journal_entries` is “journal”.
3. **Theme lifecycle:** match-only on HTTP; discover-only on CLI; empty themes ⇒ empty insights ⇒ empty chat patterns.
4. **Message invariant incomplete:** `14a4b24` stopped *matching* chat; discovery can still cluster `message` embeddings (`database.py:1053`).
5. **Gate order:** CONTEXT.md enablement → confidence → **conflict → rank → budget**; runtime enablement → confidence → **budget** → conflict → rank → budget again.
6. **Non-interpretive contract** vs `KIND_MAP` `"causal"`, `_iris_read` copy, and `SYSTEM_PROMPT` “triggered” example. Firewall covers templates only.
7. **Body:** mocks show Fitbit/HRV/aFib; API tells the truth (`kind: none`); missing overview routes 404 when mocks off.
8. **Connectors “connected”** with no backend; Settings “forget/export/delete” copy with no handlers; `DELETE /api/knowledge/{id}` **does** delete themes if called.
9. **Mood vs energy vs sleepHours=0** on the review contract.
10. **`NARRATIVE_FAIL_MODE` and several `.env.example` flags** are not read.
11. **`OPENAI_MODEL` ignored** by `PersonalAICompanion` and review letter.
12. **Onboarding** backend exists; UI is a stub; app does not gate on `onboarding_completed`.
13. **Conversation IDs** are decorative; one rolling transcript.
14. **Habit skip** is processed as a `habit_completion` occurrence.
15. **CONTEXT “sources immutable”** vs reflection PUT/DELETE.
16. **Local-first privacy copy** vs all embeddings/chat/review going to OpenAI when a key works.
17. **SSE “streaming”** is post-hoc word splitting.

---

## 7. New findings missed by the original review

Important issues **not named** (or only implied) in original R0, confirmed now:

| ID | Issue | Who found it | Why it matters |
|---|---|---|---|
| N1 | **`discover_themes()` never runs on the HTTP ingest path** | R2 (Critical); R1 map | SPA-only users never form themes. This is the product loop breaker R0 did not title. |
| N2 | **`JournalEntry` `journals` NameError** | R1 + R2 | CLI `/journal` is dead; tests that call `db.create_journal_entry` stay green. |
| N3 | **Discovery still clusters chat embeddings** after `14a4b24` | R1 + R2 | The HEAD fix is incomplete. |
| N4 | **Hatch wheel omits API/CLI modules** | R2 | `uv pip install .` would not ship `iris_api.py` / `companion.py`. |
| N5 | **`conversation_id` ignored** | R2 | Contract pretends there are conversations. |
| N6 | **Habit skips become theme evidence** | R2 | Skipping yoga can reinforce a Yoga theme. |
| N7 | **hdbscan not installed; sklearn DBSCAN fallback** | R1 | Theme discovery quality ≠ documented HDBSCAN. |
| N8 | **Fake SSE** | R1 | TTFT = full LLM latency; proxies may time out. |
| N9 | **Settings forget/export/delete unwired** (R0 mentioned connectors catalog, not the dead privacy buttons) | R1 + R2 | Privacy copy is false. |
| N10 | **Onboarding UI stub / ungated app** | R1 + R2 | First-run flow is fiction. |
| N11 | **IVFFlat created on empty tables** | R1 + R2 | Silent bad recall, not a crash. |
| N12 | **Health-invariant test requires live OpenAI** | R1 + coordinator | HEAD’s 134/134 is not an offline fact. |
| N13 | **`iris_test_db` leftovers (14 users / 45 reflections / 41 embeddings)** after “isolated” suite | R1 + R2 | `_purge_user` is per-fixture; some tests never use it. |
| N14 | **Reflections mutable / hard-delete orphans** vs CONTEXT immutability | R2 | Embedding/occurrence orphans. |
| N15 | **`frontend/.env.local` comment still wrong after “WIRED LIVE”** (R0 had LI-11; still true, and insights/review *are* live contrary to the comment) | both | Mixed mock/live is the demo footgun. |

R0 **did** catch the ingest identity bug, dual journals, gate order, body mocks, docs/Docker drift, and test-vs-live-DB — those are not “missed,” but several of them were marked fixed or deferred and are still open.

---

## 8. Original-review false positives or obsolete conclusions

Treat these as **obsolete relative to commit `14a4b24`**, not as attacks on R0’s original snapshot.

| R0 claim | Why obsolete |
|---|---|
| Two auth models / JWT in query / default `SECRET_KEY` / `python-jose` | Removed in `9d97803`. Residual issue is **no auth + Docker 0.0.0.0**, which is a different design. |
| Neo4j required at import; compose Neo4j healthcheck mismatch | Removed in `c591509`. |
| CORS wildcard + credentials | Middleware gone. |
| Tests mutate `iris_db` | Redirected to `iris_test_db` with a name guard (`b4bdcec`). Isolation is still incomplete, but the original Critical data-loss path to personal data is closed **if** the guard holds. |
| Uncommitted SPA and insights service | Snapshotted in `70bf1d2`. |
| Four named resolution-cache failures as the live red suite | Those four are not the current failures. Root cause of the old four was LI-34 (chat-as-occurrence), claimed fixed. |
| Duplicate CLI file `q` | Deleted. |
| Git remote `Host gh` (OD-22) | `origin` is now `git@github.com:noodisD/Iris-01.git`. |
| “Process cannot start if Postgres is down” (LI-8 correction) | Lazy pool `9e9ac89`: import succeeds; `/health` still does not probe. |
| LI-24 “API tests pass while embeddings silently fail” as the *live-key* behavior | R0 later corrected that a live key **does** embed. Dummy-key behavior still matches the original LI-24. Both statements can be true in different environments. |
| “User not in docker group” as accidental drift | R0 later called this Omarchy policy. Socket is still unusable without sudo; not a repo bug. |
| “No surviving dataset” then “Rails DBs in postgres18 container” | R0 self-corrected. `iris_db` exists and is nearly empty (1 user, 2 messages). |

R0 was **not** a false-positive-heavy review. Its main failure mode vs *today* is **staleness after its own remediation**, plus under-naming the HTTP discover gap and the CLI `journals` NameError.

---

## 9. Disagreements and adjudication

### 9.1 Which test failed? (R1 vs R2)

- **R1:** 132 passed, 1 failed — `test_system_health_invariant` (`assert 0 == 1`), dummy OpenAI key.
- **R2:** 132 passed, 1 failed — `test_complete_journal_entry_flow` expected new journal text, got leftover `'Stress 0'`.
- **HEAD/R0:** 134 passed.

**Evidence that resolves it:** the two failures are **both real**, **environment-dependent**, and **not contradictory**.

- Coordinator re-run with dummy key: health-invariant **fails** (5 identical reflections → 0 patterns because embeddings 401 → `discover_themes` no-ops).
- Coordinator re-run of e2e in isolation: **passes** because `iris_test_db` currently has **0** `journal_entries`. R2’s failure requires leftover pending rows — which the unscoped `LIMIT 1` query will pick. R1 and R2 also likely overlapped pytest on the same DB.

**Remains unresolved:** whether the full suite is green with a **live** key on a **truncated** `iris_test_db`. That experiment was not run (cost + mutation).

### 9.2 Severity of “no HTTP discover” (R2 Critical vs R1 not titled Critical)

**Adjudicated: Critical for a SPA-only product.** Code is unambiguous: no `discover_themes` in `iris_api.py`; `check_persistence` cannot create the first theme. R1 described the architecture correctly but under-weighted the end-to-end consequence. R2 is right on severity for the intended UI.

### 9.3 Severity of gate order (R1 High vs R2 Medium)

**Adjudicated: High.** CONTEXT.md and `budget_gate`’s own comment contradict runtime. Whether users *notice* depends on having >5 insights — which a new SPA user currently cannot, because of N1. The logic bug is still High; its production blast radius is currently masked by empty themes.

### 9.4 `google-generativeai` Medium vs High

**Adjudicated: Medium.** SDK is EOL (verified). Companion never enables Gemini. Impact is unused-fallback / install-surface, not the primary path.

### 9.5 Unauthenticated API as Critical

**Adjudicated: High for the documented Docker path; Medium for the actual `__main__` loopback path.** Owner decided single-user localhost. Dockerfile/README still publish `0.0.0.0:8000`. The code path you *run as documented in README* is Critical; the code path you *run as `python iris_api.py`* is loopback.

### 9.6 Route counts (46 vs 53)

**Resolved:** 53 FastAPI route **objects**; ~46 unique paths. Both counted honestly.

### 9.7 What all three failed to verify

- Browser E2E of SPA workflows.
- `npm run build` freshness vs `frontend/src`.
- `docker build` actual compiler error text (static COPY failure is enough to call it broken).
- Live `gpt-4.1-mini` availability on this API key.
- IVFFlat `EXPLAIN` / recall.
- Concurrent pipeline race (logic is clear; not stress-tested).
- GitHub Issues.
- Contents of the 2 live `iris_db` messages (intentionally unread).
- Whether `iris_rails_*` should share this Postgres.

---

## 10. Consolidated risk register

### Critical

| ID | Risk | Basis |
|---|---|---|
| C1 | Wrong-item embedding attribution (unscoped fetch) | pipeline + `get_items_to_process`; dirty-DB test failure |
| C2 | SPA never forms themes (no HTTP `discover_themes`) | CLI-only discover + empty-theme short-circuit |
| C3 | Documented Docker deploy cannot build and would bind 0.0.0.0 with no auth | Dockerfile + README + CMD |
| C4 | Silent empty product loop (ingest errors swallowed; insights stay `[]`) | pipeline `except`; reflection `print`; tests green |

### High

| ID | Risk | Basis |
|---|---|---|
| H1 | Dual journal stores; CLI journal NameError | `iris_api.py` mapping; `journal_entry.py:61` |
| H2 | Chat-as-evidence hole in `discover_themes` | `get_unassigned_embeddings` includes `message` |
| H3 | Fabricated biometrics / mixed mocks | `body.ts`, `.env.local`, missing overview routes |
| H4 | Gate order vs CONTEXT | `core.py` registers budget as gate 3 |
| H5 | Privacy UI lies (connectors, forget, export, “on this device”) while OpenAI sees text | Settings + Intelligence |
| H6 | Default pytest can bill OpenAI; `iris_test_db` not fully purged | live test in collection; leftover counts |
| H7 | No real migrations; missing CASCADE; embedding orphans | `create_schema`; `_purge_user` comments |
| H8 | Stale ops scripts (wrong DB names, wrong systemd path) | `setup_db.sh`, `iris.service.example` |
| H9 | SHA-256 leftover + default `local`/`local` | `hash_password`; `IRIS_DEFAULT_*` |
| H10 | LLM errors stored as Iris’s voice | `intelligence.py` + `memory.add_message` |

### Medium

| ID | Risk | Basis |
|---|---|---|
| M1 | Timezone-naive engine windows | HEAD M3.3; `datetime.now()` vs TIMESTAMPTZ |
| M2 | Pool maxconn=5 | `database.py` |
| M3 | `/health` ignores Postgres | `iris_api.py:190–193` |
| M4 | EOL Gemini SDK still installed | `google-generativeai==0.8.6` |
| M5 | Model/config split; dead feature flags | `OPENAI_MODEL`, `NARRATIVE_FAIL_MODE` |
| M6 | Two preference systems | `user_preferences` vs `user_app_settings` |
| M7 | Fake SSE; sync embed+LLM on the request | stream endpoint |
| M8 | IVFFlat on empty tables | lists=100, n=2 |
| M9 | Habit skips as occurrences; color/supports fictional | trackers + schema |
| M10 | conversation_id unused; onboarding ungated | API vs SPA |
| M11 | No CI; 1584 ruff / 410 mypy (R2 counts) | tooling never gated |
| M12 | Hatch packaging omits entrypoints | `packages = ["agent"]` |
| M13 | PG16 compose vs PG18 host; leftover Neo4j env keys | compose / `.env` |
| M14 | Latent SQL identifier interpolation | `update_preference` |
| M15 | Forget-theme does not delete embeddings | `delete_theme` |

### Low

| ID | Risk | Basis |
|---|---|---|
| L1 | pydantic `.dict()` | two call sites |
| L2 | Missing `docs/adr/` | domain skill |
| L3 | Dead modules (`engine_base`, `narrative_system`) | unused |
| L4 | CLI `\1` logs; `/rebuild-vector` help only | `companion.py` |
| L5 | Suggestion accept 204 | insights API |
| L6 | Archive docs point at deleted HTML | archive README |
| L7 | Duplicate dev-dep declaration; undeclared `httpx` | pyproject vs lock |
| L8 | Module-level OpenAI embeddings proxy vs `OpenAI()` client | `pipeline.py` vs `intelligence.py` |

---

## 11. Unknowns requiring owner clarification

Ask only questions that change diagnosis or recovery order:

1. **Is the Python monolith still the product**, given `/home/noodis/learning/iris-rails` on the same Postgres? (R0 called it a 3-minute scaffold; confirm.)
2. **Should theme discovery run automatically after ingest**, or is CLI `/discover` an intentional human gate?
3. **One journal model:** keep SPA→reflections and retire `journal_entries`, or the reverse?
4. **Body screen:** implement empty honest states, hide the route, or actually integrate a wearable?
5. **Keep the CLI** as a second product, or delete/login-strip it to match single-user HTTP?
6. **Keep Gemini** (requires `google-genai` migration) or delete the fallback?
7. **Python target:** stay on 3.11.9, or align black/mypy/runtime on 3.13/3.14?
8. **Rotate the OpenAI key** sitting in `.env` through the dormant period?
9. **How should Docker be reached on Omarchy** (sudo/polkit vs group), and is container deploy still wanted at all given the systemd decision?
10. **May tests use a live OpenAI key in default `pytest`?** If no, the health-invariant test and several API tests must be mocked or marked `live`.

---

## 12. Prioritized recovery roadmap

Nothing below has been executed in this audit.

### Phase 0 — Preserve and reproduce the current state

Already largely done (`70bf1d2` snapshot, branch pushed per R0). Remaining:

| # | Action | Verification |
|---|---|---|
| 0.1 | Keep working on `recovery/2026-09-06-baseline`; do not mix with `main` until docs match | `git status` clean; HEAD = `14a4b24` or descendant |
| 0.2 | Record that `iris_db` is nearly empty (no dump required unless the 2 messages matter) | `SELECT count(*)` snapshot |
| 0.3 | Treat `iris_test_db` leftovers as disposable test residue, not user data | name contains `test` |

### Phase 1 — Restore build and startup

| # | Action | Verification |
|---|---|---|
| 1.1 | Rewrite README for: uv, `.venv` Python 3.11.9, `python iris_api.py` on 127.0.0.1:8000, native Postgres 5432, `frontend/` SPA | A stranger can boot from README |
| 1.2 | Either **delete** Dockerfile/compose or rewrite for uv + `frontend/dist` + `127.0.0.1` publish | `docker build` is not a required path unless you keep compose |
| 1.3 | Fix `scripts/iris.service.example` to this repo path and `uvicorn iris_api:app --host 127.0.0.1` | `systemd-analyze verify` |
| 1.4 | Confirm API start: `/health` **and** `/api/user` 200 against `iris_db` | not just import |

### Phase 2 — Restore core workflow correctness

| # | Action | Verification |
|---|---|---|
| 2.1 | Fetch-by-id in the pipeline (`WHERE id = %s`); refuse mismatch | Two pending rows; process id B; embedding text = B |
| 2.2 | Decide and implement first-theme creation on HTTP (async `discover_themes` or match-or-create) | Empty DB → 5 SPA journals → `themes` > 0 → `/api/insights` nonempty **with mocked embeddings** |
| 2.3 | Exclude `message` (and habit **skips**) from `get_unassigned_embeddings` / occurrence writes | Chat + discover does not resurrect dissipation |
| 2.4 | Pick one journal store; fix or delete `JournalEntry` | POST `/api/journal` populates the store chat context reads |
| 2.5 | Remove duplicate `BackgroundTask` on `POST /api/reflections` | `generate_embedding` called once |
| 2.6 | Move budget after conflict+rank | 6 engines, `max_items=3` → highest priority survive |
| 2.7 | Honest Body/Today: empty state from `/api/body/source`; never ship mock HRV/aFib in `frontend/dist` | `VITE_USE_MOCKS=false` does not 404; no `Fitbit Air` in production bundle |

### Phase 3 — Security and compatibility

| # | Action | Verification |
|---|---|---|
| 3.1 | Keep loopback; refuse `0.0.0.0` unless an explicit flag | Dockerfile/README cannot advertise open bind |
| 3.2 | Drop or argon2 the leftover password hash; do not default `local`/`local` in any networked path | no SHA-256 KDF |
| 3.3 | Rotate OpenAI key if Q8 is yes | app works with new key |
| 3.4 | Drop Gemini **or** migrate to `google-genai` | `uv tree` has no `google-generativeai` |
| 3.5 | UTC-aware engine clocks | freeze-time identical under `TZ=UTC` and `Europe/Warsaw` |
| 3.6 | Versioned migrations; CASCADE / embedding ownership | `DELETE FROM users` either cascades or is refused cleanly |
| 3.7 | Whitelist keys in `update_preference` | bogus key never reaches SQL |

### Phase 4 — Align tests, documentation, tooling

| # | Action | Verification |
|---|---|---|
| 4.1 | `pytest.mark.live` default-ignore; mock `generate_embedding` in API tests; session-level wipe of `iris_test_db` | dummy key: full non-live suite green; `iris_db` row counts unchanged |
| 4.2 | Rewrite ARCHITECTURE/CONTEXT field names; add ADRs for single-user, pgvector-only, no-Neo4j, journal mapping, messages≠occurrences | docs match code |
| 4.3 | Delete or quarantine dead modules and stray root files | no second narrative/engine story |
| 4.4 | Wire or remove onboarding, connectors, forget/export, suggestion accept | no dead buttons |
| 4.5 | Unify `OPENAI_MODEL`; make `NARRATIVE_FAIL_MODE` real or delete it | env changes behavior |
| 4.6 | CI: `uv sync --frozen`, pytest vs service Postgres, `tsc`/`npm run build` | green on the recovery branch |
| 4.7 | Fix CLI logs / help / login **or** remove CLI from Quick Start | `/journal` either works or is gone |

### Phase 5 — Optional modernization

Vite 8 / React 19, async DB or larger pool, HNSW instead of empty IVFFlat, journal/reflection unification polish, analytical prefs in the SPA, packaging layout so the hatch wheel is complete. **Do not start here.**

---

## 13. Recommended first actions

**Mandatory restoration — smallest safe sequence to a known, reproducible, testable state:**

1. **Freeze this commit as the known snapshot** (`14a4b24`). Do not “clean up” docs and ingest in the same unreviewed pile.
   - Verify: `git rev-parse HEAD` unchanged until an approved fix branch.
2. **Stop following README Docker as if it worked.** Local path only: existing `.venv` + Postgres 5432 + `python iris_api.py`.
   - Verify: `GET /health` 200 **and** `GET /api/user` 200.
3. **Fix pipeline identity (C1)** before running the full suite again on a dirty `iris_test_db`.
   - Verify: two pending rows test described in 2.1.
4. **Mock embeddings in default pytest; mark `test_live_system.py` and `test_system_health_invariant` as live** (or give the invariant a mock embed). Truncate/recreate `iris_test_db` per session.
   - Verify: `OPENAI_API_KEY=invalid pytest tests/ --ignore=tests/test_live_system.py` is 0 failed, 0 skipped-unexpected; `iris_db` counts unchanged.
5. **Decide Q2 (HTTP discover) and implement the minimum** so five journal posts can create a theme **in tests with mocks**.
   - Verify: mocked ingest test, not a billed live run.
6. **Rewrite README to the monolith that actually exists** so the next agent does not resurrect Poetry/Chroma/Vanilla.

**Explicitly optional (do not conflate with restoration):** Vite major bump, Gemini migration, K8s/`origin/dev`, argon2 if the CLI is being deleted anyway, packaging wheel layout, ruff/mypy zero.

**Verification criteria for “known testable state”:** dummy-key suite green; pipeline id-safe; README steps boot the API against `iris_db` without Docker; `git status` only shows intended edits.

---

## Artifacts

| File | Role |
|---|---|
| `/tmp/iris-audit-2026-09-06/original-review-r0.md` | R0 |
| `/tmp/iris-audit-2026-09-06/auditor-a-report.md` | R1 (45 findings) |
| `/tmp/iris-audit-2026-09-06/auditor-b-report.md` | R2 (42 findings) |
| `/tmp/iris-audit-2026-09-06/r0-finding-catalog.md` | coordinator R0 index |
| `/tmp/iris-audit-2026-09-06/final-consolidated-report.md` | this document |

**Project tree was not modified.** `git status --porcelain` is empty. Waiting for explicit approval before any remediation.


# Part 2 — Auditor A (R1) complete report

# IRIS Ground-Zero Verification Audit — Auditor A

- **Auditor identity:** Auditor A (lens: bottom-up implementation — runtime, dependencies, build/environment, database/migrations, infrastructure, integration failures, execution-discovered errors)
- **Repository:** `/home/noodis/Iris-01`
- **Snapshot branch:** `recovery/2026-09-06-baseline`
- **Snapshot commit:** `14a4b242ae908c36b6a9ecf72ed9f1e5b39bfac3`
- **Commit subject:** `fix: stop counting chat messages as theme occurrences`
- **Investigation start:** 2026-09-06T09:10:16Z
- **Investigation end:** 2026-09-06T09:24:04Z
- **Working tree at start:** clean (`git status --porcelain` empty)
- **Working tree at end:** unmodified (see §10). Report written only to this path, outside the repository.
- **Host confirmation (read-only):**
  - Host `python3`: 3.14.7
  - `.python-version`: 3.11.9
  - `.venv` interpreter: Python 3.11.9 (`Clang 18.1.8`)
  - Package manager: uv 0.12.9
  - Docker CLI: Docker 29.7.2; **daemon socket permission denied**
  - Node: v26.8.1 / npm 11.19.0
  - PostgreSQL on `localhost:5432`: **18.6** (Debian), accepting connections
  - `localhost:5433`: no response (compose host port unused on this host)

---

## 1. Executive summary

IRIS is a **local-first personal AI companion** whose intended product is: ingest journal/reflection/habit evidence, cluster it into user-scoped **themes**, run a deterministic analytical stack (trajectory / tension / resolution / leverage / decision-impact), gate and narrate those insights, then inject them into an LLM chat. The 2026-09-06 commit series is a **mid-recovery of a 2026-06-14 snapshot**: Neo4j removed, JWT/CORS/vanilla HTML removed, tests pointed at `iris_test_db`, chat messages no longer counted as theme occurrences.

**What actually works (verified):** the Python 3.11.9 + uv environment resolves (`uv lock --check` OK); `import iris_api` succeeds with `COMPANION_AVAILABLE=True` and 53 routes; FastAPI binds loopback in the `__main__` path; pgvector 0.8.6 is installed on both `iris_db` and `iris_test_db`; frontend `tsc --noEmit` passes; 132 of 133 non-live tests pass against `iris_test_db` when OpenAI is stubbed with an invalid key.

**What does not match the advertised system:** README/ARCHITECTURE still describe a multi-user Vanilla JS + ChromaDB/FAISS + Poetry product; Dockerfile is a non-buildable Poetry artifact that copies files that no longer exist; the SPA journal writes **reflections**, not `journal_entries`; body/wearable UI is mock-only and the backend has no `/api/body/overview`; Docker/docs still recommend a compose topology that this host cannot even talk to (no docker.sock, postgres is native PG18 on 5432 not compose 5433).

**Readiness:** the analytical core is real and recently patched, but **deployment, documentation, ingest identity, and several user-facing screens are not coherent**. It is a personal local app in recovery, not a deployable multi-user product. Highest-impact issues are: broken container build, silent embedding/pipeline failure, pipeline fetch-by-status-not-id, journal dual-model, unauthenticated API if bound beyond loopback, and tests that either hit paid OpenAI or pass while ingest failed.

Finding severity counts in this report: **Critical 3, High 13, Medium 20, Low 9** (45 findings).

---

## 2. Reconstructed project purpose and architecture

### Intended users and purpose

Primary evidence (`CONTEXT.md`, `prompts/system_prompt.py`, `iris_api.py` single-user seam, commit `9d97803`):

- **User:** one person on one machine. Commit `9d97803` states “personal, local app: one process, one database, bound to loopback.”
- **Purpose:** observe long-term behavioral patterns (themes) from journals, reflections, and habits; report evidence; chat with an LLM that is supposed to treat analytical context as non-causal observation.
- **Non-interpretive contract** (`CONTEXT.md` Key Invariants): report observations, never assign causality; user-scoped; sources immutable; pipeline deterministic except LLM.

Older docs (`README.md`, `ARCHITECTURE.md`, `pyproject.toml` description) still promise a **multi-user** companion with JWT, Vanilla JS, ChromaDB/FAISS, and Docker-as-recommended-path. That is the **pre-recovery product**, not the 2026-09-06 monolith.

### Intended architecture (as of this commit)

```
SPA (frontend/, React 18 + Vite + TanStack Query)
  │  dev: :5173 proxy /api → :8000
  │  prod: FastAPI serves frontend/dist
  ▼
iris_api.py (FastAPI, single local user, no auth, no CORS)
  │
  ├─ HabitTracker / ReflectionService / InsightsService / app_settings
  ├─ PersonalAICompanion.chat()  (new instance per request)
  │     ConversationMemory → run_processing_pipeline('message')
  │     AnalysisPipeline (engines + enablement/confidence/budget gates)
  │     ConflictSuppressionEngine → InsightPrioritizationEngine
  │     NarrativeFormatter → Intelligence (OpenAI, optional unused Gemini)
  ▼
PostgreSQL + pgvector  (canonical store + vector search)
  users, journal_entries, conversation_messages, embeddings,
  themes, theme_occurrences, engine caches, habits, reflections,
  user_preferences (analytical), user_app_settings (UI)
```

CLI `companion.py` is a **second entry point** that still presents Login / Create User (multi-user) against the same database.

### Decisions that changed and were not fully propagated

| Decision (commit evidence) | Still present elsewhere |
|---|---|
| uv, not Poetry (`ce30b11`, `pyproject.toml`, `uv.lock`) | `Dockerfile` `poetry install`; `COMPATIBILITY_REPORT.md` poetry; no `poetry.lock` |
| pgvector only; FAISS/ChromaDB removed (`e387b5c`) | `README.md` / `ARCHITECTURE.md` Vector Lens; `Settings.CHROMADB_TELEMETRY`; `.env.example` `ANONYMIZED_TELEMETRY` |
| Neo4j removed (`c591509`) | live `.env` still has `NEO4J_*` keys; `tests/__pycache__/test_graph_db*.pyc` leftover |
| Single-user, no JWT/CORS, React SPA (`9d97803`) | README “multi-user HTTP Gateway”, “Vanilla JS”; `companion.py` login; `pyproject.toml` description “multi-user”; archive docs claiming `iris_frontend.html` is production |
| Chat messages are **not** theme occurrences (`14a4b24`) | `PersistenceEngine.check_persistence` docstring still says `'journal_entry' or 'message'`; `get_unassigned_embeddings` still includes `message` rows, so **discovery can still cluster chats** |
| Journal UI mapped onto reflections (`iris_api.py` `/api/journal`) | `journal_entries` table, `JournalEntry` service, CLI `/journal`, CONTEXT.md “Journal Entry” as a first-class source |
| Loopback bind (`iris_api.py` `__main__`) | `Dockerfile` `uvicorn --host 0.0.0.0`; README `docker-compose up` |

This is a **partial replacement / mid-recovery**, not a finished architecture. Commit messages on this branch are numbered M1.1 / M1.2 / M2.4 / M2.6 of a remediation sequence; several items those messages defer (timezones “M3.3”, `extract_entities` “M4.3”) remain in the tree.

---

## 3. Current-state component map

### Runtimes and toolchains

| Layer | Declared | Actual on this host |
|---|---|---|
| Python | `.python-version` 3.11.9; `requires-python >=3.11,<3.15`; mypy/black target **3.14** | venv 3.11.9; host 3.14.7 |
| Package manager | uv (`uv.lock`, 71–72 packages) | uv 0.12.9; project installed editable as `iris-minimal 0.1.0` |
| Backend | FastAPI 0.136.1, Uvicorn 0.47.0, Pydantic 2.13.4, OpenAI 2.37.0, pgvector 0.4.2, psycopg2-binary 2.9.12, numpy 2.4.5, scikit-learn 1.8.0 | matches lock |
| Frontend | React 18.3, Vite 5.4, TypeScript ^5.6.3 | `frontend/node_modules` present; tsc 5.9.3 |
| Database | compose `pgvector/pgvector:pg16` on host 5433 | **native PostgreSQL 18.6 on 5432**; `iris_db` (app), `iris_test_db` (tests), plus unrelated `iris_rails_*` |
| Containers | `docker-compose.yml` postgres+agent | Docker CLI present, **cannot talk to daemon** |
| CI | none | no `.github/` workflows |

### Entry points

1. **HTTP:** `iris_api.py` — `uvicorn.run(..., host="127.0.0.1", port=8000)` when run as `__main__`; Docker CMD uses `0.0.0.0:8000`.
2. **CLI:** `companion.py` / console script `iris = "companion:main"` — interactive login then chat loop.
3. **Frontend dev:** `frontend/` Vite `:5173` proxying `/api` to `VITE_BACKEND_URL \|\| http://localhost:8000`.
4. **Frontend prod:** FastAPI mounts `frontend/dist/assets` and SPA fallback if `frontend/dist/index.html` exists (it does on disk, gitignored).

### Backend modules (`agent/`)

| Module | Role | Notes |
|---|---|---|
| `database.py` | Singleton pool + schema + SQL | Lazy pool (`9e9ac89`); `CREATE TABLE IF NOT EXISTS` is the only “migration”; repositories exported at module end |
| `config.py` | pydantic-settings | Defaults include `POSTGRES_PASSWORD=testpassword`, placeholder OpenAI key |
| `pipeline.py` | Embed + optional persistence match | OpenAI `text-embedding-3-small`; messages embedded but not matched as of `14a4b24` |
| `persistence.py` | Theme match + HDBSCAN/DBSCAN discovery | **hdbscan is not installed**; falls back to sklearn DBSCAN |
| `trajectory.py` `tension.py` `resolution.py` `leverage.py` `decision_impact.py` | Analytical engines | Do **not** subclass unused `engine_base.py` |
| `pipeline_orchestrator.py` | Engine+gate runner | Gates registered: enablement, confidence, **budget** (before rank) |
| `conflict.py` + `conflicts.py` | Conflict suppression | Applied in `core.py` **after** the orchestrator |
| `prioritization.py` `narrative.py` `narrative_policy.py` `narrative_templates.py` | Meta-control / firewall | `narrative_system.py` has **zero importers** |
| `intelligence.py` `llm_provider.py` | OpenAI primary, Gemini fallback | Gemini path requires `use_gemini=True`; companion never passes it |
| `core.py` | `PersonalAICompanion` | Default model **`gpt-4.1-mini`**, ignoring `settings.OPENAI_MODEL` (`gpt-4o-mini`) |
| `memory.py` | Chat persistence + pipeline | New `session_id` per companion instance |
| `journal_entry.py` | Structured journal write | **`journals` is used but not imported** |
| `trackers/habits.py` `trackers/reflections.py` | Domain services | Sync `run_processing_pipeline` on write |
| `insights_service.py` | Engine output → SPA contract | Maps leverage/decision_impact to kind **`causal`** |
| `preferences.py` `preferences_guard.py` | Analytical gates | Separate from `user_app_settings` |

### HTTP surface (`iris_api.py`)

- **No auth.** `get_current_user_id()` loads or creates username `IRIS_DEFAULT_USER` default `"local"` with password `IRIS_DEFAULT_PASSWORD` default `"local"` (SHA-256).
- **Wired to SPA:** conversations (+ fake SSE), habits today/toggle/create, journal (→ reflections), settings/user/knowledge/connectors, onboarding, insights, review, body **source only**.
- **Legacy tracker API still mounted:** `/api/habits` raw list, complete/skip/calendar/weekly, full `/api/reflections*` CRUD.
- **Not implemented vs frontend contract:** `GET /api/body/overview`, `GET /api/body/day/:date`.
- **Stubs:** connectors catalog with persisted toggles and no OAuth; insight suggestion accept = 204 no-op; conversation `inferred` = `[]`.

### Data model (live `iris_db`, PG 18.6, pgvector 0.8.6)

Tables present: `users`, `journal_entries`, `conversation_messages`, `embeddings`, `themes`, `theme_occurrences`, `theme_trajectories`, `theme_tensions`, `pattern_resolutions`, `pattern_leverage`, `decision_impacts`, `pattern_confidence`, `pattern_evidence`, `insight_priorities`, `user_preferences`, `preference_audit`, `user_app_settings`, `insight_status`, `habits`, `habit_completions`, `reflections`.

Row counts at audit time (`iris_db`): 1 user (`local`), 2 conversation_messages, 2 embeddings; all analytical/habit/journal/reflection tables empty.

**FK gaps (verified `pg_constraint`):** `journal_entries.user_id`, `conversation_messages.user_id`, `themes.user_id` reference `users(id)` **without `ON DELETE CASCADE`**. `embeddings` has **no FK** to any source table.

IVFFlat indexes exist: `idx_embeddings_vector_cosine (lists=100)`, `idx_themes_centroid_cosine (lists=50)`, created in `create_schema()` on potentially empty tables.

### Frontend (`frontend/src`)

Screens: Chat, Today, Body, Journal, Habits, Insights, Review, Mobile, Settings, Onboarding. AppLayout does **not** gate onboarding. Body/Today consume `getBodyOverview()` which 404s when mocks are off. Onboarding screen is a stub that navigates to `/chat` without calling `/api/onboarding/*`. Settings “forget” × and export/delete buttons have no handlers.

`frontend/.env.local`: `VITE_USE_MOCKS=true`, `VITE_BACKEND_URL` empty. Only `src/api/body.ts` checks `useMocks()`; chat/habits/journal/insights/settings/review/onboarding always hit `/api`.

### Tests

133 tests collected excluding live; + `tests/test_live_system.py` (real OpenAI embeddings + chat). No `pytest.skip` / xfail. No frontend tests. No CI. `pytest.ini` only sets `norecursedirs = data`.

### Incomplete / abandoned / duplicated

- `archive/iris-frontend-react/` — old React app, docs still say Vanilla JS is current.
- `frontend/design-prototype/` — visual prototype; several screens marked PARTIAL PORT.
- `engine_base.py`, `narrative_system.py` — introduced in `98d62fd`, unused.
- `extract_entities()` — only test + leftover after Neo4j removal.
- `companion.py` `/rebuild-vector` listed in help, **no handler**.
- `journal-upgrade`, `23.01.2026.md`, `COMPATIBILITY_REPORT.md`, `docs/PGVECTOR_MIGRATION.md` (Flask/psycopg3) — stale artifacts.
- `docs/adr/` **does not exist** though `docs/agents/domain.md` requires it.
- Root `package-lock.json` is an empty npm lock named `personal_ai_agent_minimal`.

---

## 4. Validation commands and results

Safety notes: tests were pointed at `iris_test_db` via `IRIS_TEST_POSTGRES_DB` / conftest. **Live OpenAI was not used.** `OPENAI_API_KEY` was overridden to `sk-audit-invalid-do-not-charge` for pytest so the user’s real key was not charged. `test_live_system.py` was ignored. No compose up, no docker build (permission denied), no lock/sync/install, no writes inside the repo.

| ID | Command / method | Result | Important output | Likely cause | Unverified | Blocks others? |
|---|---|---|---|---|---|---|
| V-01 | `git rev-parse` / `git status` / `git log -1` | Pass | branch `recovery/2026-09-06-baseline`, commit `14a4b24`, clean | — | — | No |
| V-02 | `.venv/bin/python --version`; `uv --version` | Pass | Python 3.11.9, uv 0.12.9 | — | — | No |
| V-03 | `uv lock --check` | Pass | “Resolved 72 packages in 0.74ms” | lock matches pyproject | whether `uv sync` would change the venv | No |
| V-04 | `.venv/bin/python -m compileall -q agent iris_api.py companion.py prompts tests` | Pass | empty output | — | — | No |
| V-05 | `import iris_api` | Pass | `COMPANION_AVAILABLE True`; 53 routes; **no CORS middleware** | lazy PG pool | lifespan `create_schema` against live `iris_db` not executed in this import | No |
| V-06 | JournalEntry runtime | **Fail (swallowed)** | `Failed to create journal entry for user 1: name 'journals' is not defined`; method returns success-looking string path | missing import (A-LI-07) | CLI `/journal` end-to-end | No |
| V-07 | Route inventory | Pass | `/api/body/source` present; **`/api/body/overview` and `/api/body/day` absent** | never implemented | SPA behavior in browser | No |
| V-08 | `pg_isready -h localhost -p 5432` / `5433` | 5432 accepting; 5433 no response | native PG18, not compose mapping | host uses local postgres | dockerized PG | Compose path unverified |
| V-09 | Read-only `\dt` / counts on `iris_db` | Pass | schema present; 1 user `local`; 2 messages; 2 embeddings | prior local use | content of those 2 messages **not** read | No |
| V-10 | Same for `iris_test_db` | Pass | leftover rows: 6+ users, 27 embeddings, 271 `pattern_confidence`, 18 reflections, 2 themes (pre-audit); more users after health-invariant run | tests that skip `test_user` / incomplete purge | whether leftovers affect later tests | Isolation risk |
| V-11 | pytest (dummy key, ignore live) | **132 passed, 1 failed** in 26s | `tests/test_system_health_invariant.py::test_system_health_invariant` `assert 0 == 1` (0 themes surfaced for n=5) | pipeline embeddings 401 → no vectors → discover_themes no-op | **full suite with real OpenAI** (commit message claims 134/134) | Health-invariant and live E2E unverified |
| V-12 | Re-run V-11 failure `-vv` | Fail in 1.27s | User B (5 identical reflections) surfaced 0 patterns | same as V-11 | would pass with live embeddings + clustering | No |
| V-13 | `npx tsc --noEmit` in `frontend/` | Pass | TSC_EXIT 0; tsc 5.9.3 | — | runtime UI, production Vite build (would write `frontend/dist`) | No |
| V-14 | `.venv/bin/ruff check agent iris_api.py companion.py` | Fail | **1584 errors**, 872 auto-fixable | lint never gated | whether any are real bugs vs style | No |
| V-15 | `.venv/bin/mypy agent/config.py agent/constants.py` | config missing annotation | mypy `python_version = 3.14` vs runtime 3.11 | typing not enforced | full mypy | No |
| V-16 | `docker ps` / `docker build` | **Unverified** | `permission denied ... unix:///var/run/docker.sock` | user not in docker group / rootless | image build, compose health | Container path blocked |
| V-17 | `import hdbscan` | Fail | `ModuleNotFoundError` | not in `pyproject.toml` / lock | DBSCAN fallback quality | Theme discovery uses sklearn |
| V-18 | `import google.generativeai` | Loads with **FutureWarning: all support has ended** | package EOL (A-OD-03) | Gemini fallback runtime | No |
| V-19 | Frontend production `npm run build` | **Not run** | would write `frontend/dist` inside the repo | instruction: do not write in repo | dist freshness vs current `src/` | SPA production serve unverified |
| V-20 | Live chat / greeting / review letter with real LLM | **Not run** | would charge OpenAI | — | real conversational quality | Product chat unverified |
| V-21 | `tests/test_live_system.py` | **Skipped** | uses real embeddings + `companion.chat` | paid API | live E2E | No |

### Test-quality notes (passing ≠ working)

- **Paid / live API:** `tests/test_live_system.py` docstring: “Uses real OpenAI API for embeddings and chat.” `tests/test_system_health_invariant.py` creates real reflections and calls `discover_themes()` with **no embedding mock**; it only passes if OpenAI embeddings succeed. Commit `14a4b24` claims “Full suite: 134 passed” — that number is **not reproduced** without the live key.
- **API contract tests** (`test_api_habits.py`, `test_api_journal.py`, `test_api_review.py`, stream test in `test_api_chat.py`) do **not** mock `generate_embedding`. With an invalid key they still **pass**, because `HabitTracker`/`ReflectionService`/`memory.add_message` catch pipeline exceptions and continue. They assert HTTP shapes, not that themes or embeddings exist.
- **`mock_llm`** patches `agent.core.Intelligence` only. Review letter construction in `iris_api._generate_review_letter` does `import agent.core as core_module; core_module.Intelligence(...)` — that **is** patched. Chat stream uses `PersonalAICompanion.chat`, also patched. Embedding side remains live.
- **`test_system_health_invariant`** does not use the `test_user` fixture and never calls `_purge_user`, so it **leaks users** into `iris_test_db`.
- Engine/stress tests seed themes/occurrences directly and mock embeddings (`mock_pipeline_logic`). They validate math and gating, not the HTTP ingest path.
- No frontend tests; no test that `/api/journal` creates a `journal_entries` row (it does not).

---

## 5. Outdated-items register

Each item is outdated because of a **concrete compatibility, security, or operational impact**, not merely because a newer version exists.

### A-OD-01 — Product documentation describes a different system
- **Category:** Outdated docs vs implementation
- **Severity:** High
- **Evidence:** `README.md` lines 1–32 (Vanilla JS, multi-user, ChromaDB/FAISS); `ARCHITECTURE.md` lines 9–20 (Vector Lens ChromaDB/FAISS, Vanilla JS, multi-user gateway); `pyproject.toml` lines 1–4 description “multi-user”; `docs/PGVECTOR_MIGRATION.md` lines 25–36 (Flask app servers, psycopg3); `EXPLORATION_GUIDE.md` line 16 (`DatabaseConnection` class — actual class is `Database`).
- **Explanation:** The running code is FastAPI + React SPA + pgvector only + single-user, uv-managed.
- **Consequence:** A new operator following README will look for `iris_frontend.html`, Chroma, Poetry, and multi-user auth that do not exist; they will not find the real SPA or test-DB rules.
- **Confidence:** Verified
- **Recommended verification:** Diff README/ARCHITECTURE against `iris_api.py` routes and `frontend/package.json`.

### A-OD-02 — Dockerfile is a non-buildable Poetry snapshot
- **Category:** Outdated container build
- **Severity:** Critical
- **Evidence:** `Dockerfile` lines 16–26: `pip install poetry`; `COPY pyproject.toml poetry.lock ./`; `poetry install --only=main`; `COPY iris_frontend.html .`. Repository has **no** `poetry.lock` and **no** `iris_frontend.html` (`git ls-files` / `ls`). Compose `agent` service `build.target: runtime` (`docker-compose.yml` lines 24–27).
- **Explanation:** The image definition was not updated when the project moved to uv (`ce30b11`) and deleted the HTML UI (`9e9ac89`/`9d97803`).
- **Consequence:** `docker-compose up --build` (README “recommended”) cannot succeed even if Docker were usable.
- **Confidence:** Verified (static). Image build itself unverified (docker.sock denied).
- **Recommended verification:** When docker is usable, `docker build --target runtime .` and record the COPY/poetry error.

### A-OD-03 — `google-generativeai` SDK is past end-of-life
- **Category:** Outdated / unsupported SDK
- **Severity:** Medium
- **Evidence:** lock `google-generativeai=0.8.6`; `agent/intelligence.py` lines 15–22 import it and suppress FutureWarning; runtime import on 2026-09-06 emitted: “All support for the `google.generativeai` package has ended… switch to `google.genai`”. Official GitHub `google-gemini/deprecated-generative-ai-python` archived 2025-12-16; README support ended **2025-11-30**. Verification date **2026-09-06**.
- **Explanation:** Gemini is already unused in the companion path (`use_gemini` default False), but the dependency still installs a dead SDK.
- **Consequence:** Fallback provider cannot be maintained; FutureWarning on import; any future Gemini enablement will break.
- **Confidence:** Verified
- **Recommended verification:** https://github.com/google-gemini/deprecated-generative-ai-python and `pip show google-generativeai`.

### A-OD-04 — Install/deploy scripts name databases, users, and paths that do not exist
- **Category:** Outdated ops docs
- **Severity:** High
- **Evidence:** `scripts/setup_db.sh` creates user `iris_app` and database **`iris_agent`** on port **5432**; live config is `iris_user` / `iris_db` / `.env` port **5432** while `.env.example` and `docker-compose.yml` advertise **5433**. `scripts/iris.service.example` lines 8–12: `WorkingDirectory=/home/noodis/Myself/apps/personal_ai_agent_minimal`, `ExecStart=.../companion.py`. `COMPATIBILITY_REPORT.md` still says “re-run poetry”.
- **Explanation:** leftover from an earlier tree (`personal_ai_agent_minimal`).
- **Consequence:** Following setup_db.sh creates the wrong database; systemd unit would not start this checkout.
- **Confidence:** Verified
- **Recommended verification:** Dry-read scripts against `.env.example` and `agent/config.py`.

### A-OD-05 — Password storage is unsalted SHA-256
- **Category:** Outdated crypto
- **Severity:** High (CLI / leftover user table) / Medium under current “no login” API
- **Evidence:** `agent/database.py` lines 24–26 `hashlib.sha256(password.encode()).hexdigest()`; `users.password_hash VARCHAR(256)`; live `iris_db` user `local` hash length 64 (hex SHA-256). JWT/python-jose removed in `9d97803` but hashing remains for `create_user` / CLI login.
- **Explanation:** SHA-256 without salt is not an acceptable password KDF (no unique salt, no work factor).
- **Consequence:** If the DB leaks, passwords are trivially cracked; default `"local"`/`"local"` is especially weak.
- **Confidence:** Verified
- **Recommended verification:** `hash_password` + `verify_user` unit test; confirm no bcrypt/argon2 in lockfile.

### A-OD-06 — Pydantic v1 `.dict()` still used on v2 models
- **Category:** Deprecated API
- **Severity:** Low
- **Evidence:** `iris_api.py` lines 455 and 612 `updates.dict(exclude_none=True)` on `HabitUpdate` / `ReflectionUpdate`. Locked pydantic **2.13.4**. `.dict()` is a deprecated alias for `model_dump()`.
- **Explanation:** still functions in 2.13; will break when the alias is removed.
- **Consequence:** habit/reflection PATCH/PUT would start raising after a pydantic major cleanup.
- **Confidence:** Verified
- **Recommended verification:** pydantic 2 deprecation warnings with `PYTHONWARNINGS=default`.

### A-OD-07 — Tooling targets Python 3.14 while the supported runtime is 3.11.9
- **Category:** Toolchain mismatch
- **Severity:** Medium
- **Evidence:** `.python-version` = `3.11.9`; `pyproject.toml` `[tool.black] target-version = ['py314']`; `[tool.mypy] python_version = "3.14"`; host python3 is 3.14.7; `COMPATIBILITY_REPORT.md` documents 3.14 packaging failures (pypika/onnxruntime — those packages are **not** in current lock).
- **Explanation:** running the app with host `python3` (3.14) is outside the tested venv; black/mypy assume 3.14 syntax/stdlib.
- **Consequence:** onboarding confusion; typecheck may accept 3.14-only constructs the venv cannot run (not observed in this snapshot).
- **Confidence:** Verified
- **Recommended verification:** `black --check` / `mypy` full tree under 3.11.

### A-OD-08 — Compose Postgres 16 vs host Postgres 18; leftover Neo4j env
- **Category:** Environment drift
- **Severity:** Medium
- **Evidence:** `docker-compose.yml` image `pgvector/pgvector:pg16`; host `SELECT version()` → PostgreSQL **18.6**; pgvector extension **0.8.6**. Live `.env` still defines `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` (keys only inspected); `.env.example` does not; `graph_db.py` deleted in `c591509`.
- **Explanation:** app talks to whatever is in `.env` (here native PG18:5432). Compose, if ever used, would be a different major and port.
- **Consequence:** two incompatible “official” DB topologies; Neo4j secrets still sitting in env for a removed component.
- **Confidence:** Verified (host). Compose image behavior unverified.
- **Recommended verification:** official pgvector PG18 support matrix; start compose only in an isolated project.

### A-OD-09 — Domain ADR layout never created
- **Category:** Outdated process docs
- **Severity:** Low
- **Evidence:** `docs/agents/domain.md` lines 7–15 require `docs/adr/ADR-0000-TEMPLATE.md`; `ls docs/adr` → does not exist. `CONTEXT.md` exists at repo root.
- **Explanation:** agent-skill instructions describe a documentation system that was never stood up.
- **Consequence:** architectural decisions (Neo4j removal, single-user, uv) are only in commit messages, not ADRs.
- **Confidence:** Verified
- **Recommended verification:** `find docs -name 'ADR*'`.

### A-OD-10 — Archive frontend docs invert current vs deprecated
- **Category:** Stale archive
- **Severity:** Low
- **Evidence:** `archive/iris-frontend-react/README.md` line 3: “deprecated in favor of … Vanilla JS … `iris_frontend.html`”. That HTML was deleted in `9e9ac89`; current UI is `frontend/` React+TS.
- **Explanation:** archive warning points at a third, already-deleted UI.
- **Consequence:** anyone browsing archive is sent to a missing file.
- **Confidence:** Verified
- **Recommended verification:** `ls iris_frontend.html` (missing).

---

## 6. Logical-inconsistency register

### A-LI-01 — Frontend journal is reflections; `journal_entries` is a parallel unused model
- **Category:** Dual source of truth / workflow break
- **Severity:** High
- **Evidence:** `iris_api.py` lines 630–680 comment “frontend JournalEntry mapped onto reflections”; `POST /api/journal` → `ReflectionService.create_reflection`. `JournalScreen.tsx` posts `{lines, mood}`. Canonical `journal_entries` is only written by `agent/journal_entry.py` (CLI) and tests. Chat context loads **both** `journals.get_reflections` and `journals.get_recent_entries` (`core.py` `_get_reflections_context` / `_get_recent_journal_entries_context`).
- **Explanation:** the SPA “journal” never creates `journal_entries` rows. Theme ingest for the UI path is `source_type='reflection'`. CONTEXT.md still treats Journal Entry as the primary source with `raw_text` + vector.
- **Consequence:** CLI and UI write different tables; “recent journal entries” in the LLM prompt stay empty for SPA users; tests of `journal_entry` flow do not cover the product UI.
- **Confidence:** Verified
- **Recommended verification:** POST `/api/journal` then `SELECT count(*) FROM journal_entries` vs `reflections`.

### A-LI-02 — Chat messages excluded from occurrence matching but still eligible for theme discovery
- **Category:** Partial replacement
- **Severity:** High
- **Evidence:** `agent/pipeline.py` lines 122–133 (`should_check_persistence = source_type in ['journal_entry', 'reflection', 'habit_completion']`) — commit `14a4b24`. `agent/database.py` `get_unassigned_embeddings` lines 1049–1053 still includes `source_type = 'message' AND role = 'user'`. `PersistenceEngine.discover_themes()` clusters **all** unassigned embeddings. `check_persistence` docstring line 118 still says `'journal_entry' or 'message'`.
- **Explanation:** the mid-request self-evidence bug is fixed for **online matching**. Batch discovery can still create themes whose members are chat turns, which then become occurrences (discover writes `theme_occurrences` for clustered entries including messages — `persistence.py` around the cluster persist loop).
- **Consequence:** talking about a dissipated theme can still resurrect it on the next `/discover` / periodic discovery, undermining `14a4b24` and CONTEXT.md occurrence types.
- **Confidence:** Verified (code). Runtime discovery-with-messages not executed (needs embeddings).
- **Recommended verification:** embed five similar user messages, call `discover_themes()`, inspect `theme_occurrences.source_type`.

### A-LI-03 — Meta-control gate order contradicts CONTEXT.md and the budget gate’s own comment
- **Category:** Docs vs runtime / duplicated budget
- **Severity:** High
- **Evidence:** `CONTEXT.md` lines 179–180: enablement → confidence → **conflict** → prioritization → budget. `core.py` `_init_analysis_pipeline` registers enablement, confidence, **budget** (orders 1–3). `core.py` `_get_aggregated_context` then runs conflict, then `rank_insights`, then **slices `max_items` again**. `budget_gate` docstring (`pipeline_orchestrator.py` line 283): “Assumes insights are already ranked by priority” — they are not, at first call.
- **Explanation:** first budget cut is arbitrary engine-registration order; conflict never sees budgeted-out insights? Actually budget runs first so conflict sees a truncated unordered set; then rank+budget again.
- **Consequence:** high-priority conflict winners can be dropped before ranking; suppression logs disagree with CONTEXT; non-determinism vs “pipeline is deterministic”.
- **Confidence:** Verified
- **Recommended verification:** unit test with >max_items insights of mixed engines and inspect `get_suppression_log()` vs ranked output.

### A-LI-04 — Single-user HTTP vs multi-user CLI vs “multi-user” packaging
- **Category:** Product identity
- **Severity:** Medium
- **Evidence:** `iris_api.py` lines 154–170 single-user seam; `companion.py` lines 917–946 Login/Create User; `pyproject.toml` description “multi-user”; README title “multi-user”.
- **Explanation:** two apps, two identity models, one `users` table.
- **Consequence:** CLI can create extra users; API ignores them and always uses `local` (or `IRIS_DEFAULT_USER`). Data appears “missing” depending on entry point.
- **Confidence:** Verified
- **Recommended verification:** create CLI user, hit API, compare `get_current_user_id()`.

### A-LI-05 — Body screen fabricates wearables; backend honestly has none; overview route missing
- **Category:** Frontend vs backend contract
- **Severity:** High
- **Evidence:** `frontend/src/types/api.ts` BodyOverviewResponse; `frontend/src/api/body.ts` `GET /api/body/overview` and `/body/day/:date`; `iris_api.py` only `GET /api/body/source` (lines 1086–1089) returning `kind: none`. `BodyScreen.tsx` / `TodayScreen.tsx` call `useBody()` → `getBodyOverview()`. `test_api_body.py` only tests `/source`. `frontend/.env.local` `VITE_USE_MOCKS=true` and **only body.ts** honors it — so Today/Body show Fitbit-like numbers while habits/insights hit the real API.
- **Explanation:** mixed mock/live mode plus missing routes.
- **Consequence:** with mocks on, the dashboard lies about physiology. With mocks off, Body/Today error on 404. Users cannot tell which data is real.
- **Confidence:** Verified
- **Recommended verification:** `curl localhost:8000/api/body/overview` (expect 404 via SPA fallback or 404); run SPA with `VITE_USE_MOCKS=false`.

### A-LI-06 — Default LLM model is inconsistent
- **Category:** Config vs callers
- **Severity:** Medium
- **Evidence:** `agent/config.py` `OPENAI_MODEL` default `gpt-4o-mini`; `PersonalAICompanion.__init__` default `model="gpt-4.1-mini"` (`core.py` line 49) **does not read settings**; `iris_api._generate_review_letter` hardcodes `Intelligence(model="gpt-4.1-mini")` (line 1054); `persistence.py` theme summary uses `gpt-4o-mini`. Official OpenAI: both `gpt-4.1-mini` (launched 2025-04-14) and `gpt-4o-mini` exist (verification 2026-09-06).
- **Explanation:** chat/review vs embeddings/summaries vs env default disagree.
- **Consequence:** cost/behavior differ by feature; `.env` `OPENAI_MODEL` is ignored for the main companion.
- **Confidence:** Verified
- **Recommended verification:** log `Intelligence.model` on `POST /api/conversations/.../stream`.

### A-LI-07 — `JournalEntry.create_entry` references undefined `journals`
- **Category:** Broken CLI path
- **Severity:** High
- **Evidence:** `agent/journal_entry.py` imports `db` only (line 13); `create_entry` calls `journals.create_entry` (line 61). `create_entry.__code__.co_names` includes `'journals'`. Runtime: exception caught, method returns `"✗ Failed to create journal entry. Please check the logs."` rather than raising. CLI `create_journal_entry` prints that string.
- **Explanation:** leftover after repository extraction (`c06b2e0`).
- **Consequence:** CLI `/journal` cannot write; failure looks like a soft error. Tests use `db.create_journal_entry` directly, so they stay green.
- **Confidence:** Verified
- **Recommended verification:** `JournalEntry(1).create_entry(...)` (already run).

### A-LI-08 — Narrative firewall vs LLM prompt vs insights “causal” kind
- **Category:** Safety contract vs implementation
- **Severity:** High
- **Evidence:** `narrative_policy.py` forbids `\bcaus`, `should`, `trigger`, `because`, etc. `insights_service.py` `KIND_MAP` maps leverage/decision_impact to `"causal"` (lines 25–31); `_iris_read` (lines 220–225) “I keep noticing… That shift is what caught my attention.” `prompts/system_prompt.py` examples include “Did something specific happen that triggered that?” (line 25) and “Connect dots” (line 82), while later saying observations are non-causal (lines 93–96).
- **Explanation:** templates are firewalled; the LLM and the Insights UI are not. Frontend type `InsightKind` includes `'causal'`.
- **Consequence:** the “non-interpretive contract” holds only for `NarrativeFormatter` strings injected as bullets; chat and Insights copy can still advise/cause.
- **Confidence:** Verified
- **Recommended verification:** inspect an `/api/insights/:id` `irisRead`; read SYSTEM_PROMPT.

### A-LI-09 — `NARRATIVE_FAIL_MODE` setting is dead
- **Category:** Config vs code
- **Severity:** Low
- **Evidence:** `agent/config.py` `NARRATIVE_FAIL_MODE`; `.env.example` `raise | silence`; `narrative_policy.py` line 11 **hardcodes** `NARRATIVE_FAIL_MODE = "raise"`; `narrative.py` imports that constant, not `settings`.
- **Explanation:** env cannot switch fail-closed vs silence.
- **Consequence:** production `.env` `silence` does nothing.
- **Confidence:** Verified
- **Recommended verification:** set env to silence and trigger a forbidden template.

### A-LI-10 — Onboarding API is complete; onboarding UI is a stub; app does not gate on it
- **Category:** Documented-but-unimplemented UX
- **Severity:** Medium
- **Evidence:** `iris_api.py` `/api/onboarding/*` + tests `test_api_onboarding.py` (pass). `OnboardingScreen.tsx` lines 10–24: button `nav('/chat')`, comment “PARTIAL PORT … wire to api/onboarding.ts”. `AppLayout.tsx` has no redirect. `api/onboarding.ts` is unused by screens (grep).
- **Explanation:** backend ready, frontend never calls it.
- **Consequence:** `onboarding_completed` stays false; pair-body / threads answers never collected; user can use the full app immediately.
- **Confidence:** Verified
- **Recommended verification:** load `/onboarding` in the SPA; network tab.

### A-LI-11 — Connectors persist UI state with no backend integration
- **Category:** Implemented-but-undocumented-as-fake / stub
- **Severity:** Medium
- **Evidence:** `iris_api.py` lines 697–708 comment “no real OAuth/data-source backend yet”; `POST /api/connectors/{id}/{action}` writes JSON into `user_app_settings.connectors`. Settings screen cycles connect/pause/disconnect (`SettingsScreen.tsx` 18–21). Body source remains `none`.
- **Explanation:** user can “connect Fitbit Air”; nothing syncs.
- **Consequence:** false sense of wearable integration; privacy copy (“Messages: on-device sentiment”) is fictional.
- **Confidence:** Verified
- **Recommended verification:** connect a connector, GET `/api/body/source`.

### A-LI-12 — Habit color is returned on create and then forgotten
- **Category:** Contract vs persistence
- **Severity:** Low
- **Evidence:** `POST /api/habits` may set `contract["color"] = habit.color` (`iris_api.py` 387–388) but `habits` schema has **no color column** (`database.py` 475–497). `_habit_to_contract` uses `habit.get("color") or HABIT_COLORS[hid % 4]`. Subsequent `GET /api/habits/today` recomputes color from id.
- **Explanation:** create response can disagree with the next GET.
- **Consequence:** UI theme color flicker/wrong color after reload.
- **Confidence:** Verified
- **Recommended verification:** POST color `rose`, GET `/today`, compare `color`.

### A-LI-13 — Two preference systems; Settings UI never touches analytical gates
- **Category:** Duplicated sources of truth
- **Severity:** Medium
- **Evidence:** `user_preferences` (min_confidence, max_items, enabled_engines) vs `user_app_settings` (tone, density, check-in times, connectors, onboarding). Settings screen patches `/api/user/preferences` (app settings only). CLI `/settings` uses `UserPreferencesService`.
- **Explanation:** the SPA cannot set the gates that actually filter chat context.
- **Consequence:** CONTEXT.md “preferences never override safety… take effect on next chat” is CLI-only.
- **Confidence:** Verified
- **Recommended verification:** PATCH `/api/user/preferences` then inspect `user_preferences` table.

### A-LI-14 — `/rebuild-vector` advertised, not implemented
- **Category:** Dead CLI
- **Severity:** Low
- **Evidence:** `companion.py` `show_help` line 72; no `elif` for `/rebuild-vector` in the command loop (grep `rebuild` only hits the help string). Graph rebuild was removed with Neo4j (`c591509`).
- **Explanation:** leftover help text.
- **Consequence:** command falls through to `companion.chat("/rebuild-vector")` and may send that to the LLM.
- **Confidence:** Verified
- **Recommended verification:** type the command in CLI.

### A-LI-15 — Unused architecture leftovers from the May refactor
- **Category:** Dead code / partial replacement
- **Severity:** Low
- **Evidence:** `engine_base.py` — only self-references (grep). `narrative_system.py` — zero importers. `extract_entities` — test + definition; Neo4j consumers deleted (`c591509` message). `companion.py` still filters `hdbscan` DeprecationWarning though hdbscan is not installed.
- **Explanation:** `98d62fd` / `c06b2e0` introduced parallel structures never adopted by engines (`TrajectoryEngine` etc. remain standalone classes).
- **Consequence:** two “how to add an engine” stories (CONTEXT seams vs engine_base vs orchestrator register).
- **Confidence:** Verified
- **Recommended verification:** `rg AnalyticalEngine` / `rg narrative_system`.

### A-LI-16 — `POST /api/reflections` runs the pipeline twice
- **Category:** Duplicate processing
- **Severity:** Medium
- **Evidence:** `ReflectionService.create_reflection` already calls `run_processing_pipeline('reflection', id)` (`reflections.py` 76–80). `iris_api.py` 543–565 also `background_tasks.add_task(run_processing_pipeline, 'reflection', reflection_id)`. SPA journal uses `/api/journal` (sync only). Legacy reflections API double-fires.
- **Explanation:** status goes processing→complete then background sets processing again and re-embeds.
- **Consequence:** extra OpenAI cost; interacts with A-R-04 (fetch by status).
- **Confidence:** Verified
- **Recommended verification:** instrument `run_processing_pipeline` call count on POST `/api/reflections`.

### A-LI-17 — SSE “streaming” is word-chunking of a completed reply
- **Category:** Contract vs runtime
- **Severity:** Medium
- **Evidence:** `iris_api.py` 290–317: `run_in_threadpool(companion.chat, text)` then `for word in reply.split(" ")`. `frontend/src/api/client.ts` 59–64 comments `event: token` but parser only reads `data:` lines (works with backend). `useChat.ts` updates token-by-token.
- **Explanation:** UX shows a stream; TTFT equals full LLM latency. Not a protocol bug, but contradicts “streaming reply”.
- **Consequence:** timeouts/proxies may kill the request while the model is still running; user sees a long hang then a burst.
- **Confidence:** Verified
- **Recommended verification:** observe network waterfall on send.

### A-LI-18 — Compose port / `.env.example` / frontend example URL disagree
- **Category:** Config across environments
- **Severity:** Medium
- **Evidence:** compose publishes `5433:5432`; `.env.example` `POSTGRES_PORT=5433`; live `.env` `POSTGRES_PORT=5432` (length-4, settings printed 5432); `frontend/.env.example` `VITE_BACKEND_URL=http://localhost:8080`; API is **8000**; `iris_api.py` / Vite proxy default 8000.
- **Explanation:** three ports (5432/5433, 8000/8080) documented.
- **Consequence:** following examples fails to connect.
- **Confidence:** Verified
- **Recommended verification:** start API, hit 8000 vs 8080.

### A-LI-19 — Settings “forget / export / delete” controls are non-functional
- **Category:** UI vs API
- **Severity:** Medium
- **Evidence:** `SettingsScreen.tsx` lines 34–35 buttons `export everything` / `delete & forget` have no `onClick`. Forget × (line 49) has `aria-label="forget"` and **no handler**; `forgetFact` in `api/settings.ts` is unused by the screen (grep). Backend `DELETE /api/knowledge/{id}` exists and **does** delete a theme.
- **Explanation:** API can forget; UI cannot.
- **Consequence:** copy claims “If you ever want me to forget — half, or all — that is a button” (`SettingsScreen.tsx` 80) while the button does nothing. Privacy promise is false.
- **Confidence:** Verified
- **Recommended verification:** click × in Settings; confirm no DELETE.

---

## 7. Risk register

### A-R-01 — Unauthenticated API; default credentials; Docker binds 0.0.0.0
- **Category:** Security / authorization
- **Severity:** Critical (if compose/Dockerfile used as README instructs); High on loopback-only
- **Evidence:** no auth dependencies on 45+ `/api/*` routes (import inventory). `DEFAULT_USERNAME`/`DEFAULT_PASSWORD` (`iris_api.py` 161–162) default `"local"`. Dockerfile CMD `uvicorn iris_api:app --host 0.0.0.0 --port 8000`. README “Deploy via Docker (Recommended)” / “Access the app at http://localhost:8000”. Local `__main__` binds `127.0.0.1` (good).
- **Explanation:** any client that can reach the port is the user. Compose publishes 8000.
- **Consequence:** LAN/WAN exposure of journal, chat, and OpenAI-backed companion; anyone can delete knowledge (`DELETE /api/knowledge/{id}`).
- **Confidence:** Verified (code). Network exposure unverified (compose not started).
- **Recommended verification:** bind scan; `curl` from another host if compose is up.

### A-R-02 — Processing pipeline fetches “any row with status=processing”, not the requested id
- **Category:** Data integrity
- **Severity:** Critical
- **Evidence:** `run_processing_pipeline` (`pipeline.py` 77–81) sets **this** `source_id` to `processing`, then `get_items_to_process(source_type, status='processing', limit=1)` **without `WHERE id = source_id`** (`database.py` 764–880). Embedding is stored under the **original** `source_id` using **fetched** content.
- **Explanation:** concurrent writes, or double-schedule (A-LI-16), can attach the wrong text/vector to an id and leave the other row stuck in `processing`.
- **Consequence:** silent corruption of embeddings and theme matches; hard to detect; paid embedding of the wrong object.
- **Confidence:** Verified (code). Concurrency not load-tested.
- **Recommended verification:** two overlapping `run_processing_pipeline` calls; assert embedding text == source text.

### A-R-03 — Embedding/LLM failures are swallowed; user-facing paths still “succeed”
- **Category:** Silent failure
- **Severity:** High
- **Evidence:** `HabitTracker.create_habit` / `log_completion` `except: print(...)` (`habits.py` 40–43, 85–88). Same in `reflections.py` 77–80. `memory.add_message` logs pipeline errors and keeps the message (`memory.py` 66–73). `Intelligence.chat` returns `"Error calling API: ..."` strings (`intelligence.py` 178–179) which `core.chat` **persists as assistant content**. Greeting endpoint returns a hardcoded fallback (`iris_api.py` 209–210); proactive returns `"..."` (line 231). pytest V-11: API tests **passed** while embeddings 401’d.
- **Explanation:** HTTP 200 + empty analytics is the common failure mode without a live key or during outages.
- **Consequence:** user thinks IRIS is learning; themes never form; chat history may contain raw API error text.
- **Confidence:** Verified
- **Recommended verification:** run SPA journal/habit with invalid OpenAI key; inspect `embeddings` and `conversation_messages`.

### A-R-04 — No migration system; `CREATE IF NOT EXISTS` cannot evolve constraints
- **Category:** Schema / recoverability
- **Severity:** High
- **Evidence:** `Database.create_schema` (`database.py` 131–559) is the only migrator. Additive `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for some habit columns. **Cannot** add `ON DELETE CASCADE` to existing `journal_entries`/`themes` FKs. `scripts/setup_db.sh` comments “assumes alembic” but there is no alembic, no `scripts/schema.sql`.
- **Explanation:** production DBs (this host’s `iris_db`) already have the weaker FKs.
- **Consequence:** schema drift between fresh test DB and long-lived user DB; destructive changes have no rollback.
- **Confidence:** Verified
- **Recommended verification:** compare `pg_constraint` on a freshly `create_schema()` DB vs `iris_db`.

### A-R-05 — Missing ON DELETE CASCADE and embedding FKs → orphans / failed user delete
- **Category:** Data integrity
- **Severity:** High
- **Evidence:** live FKs listed in §3; `tests/conftest.py` `_purge_user` comment lines 90–97 explicitly: journal entries, messages, themes do not cascade; embeddings keyed by source not user. `delete_theme` (`database.py` 970–977) deletes theme (occurrences cascade) but **not** embeddings.
- **Explanation:** `_purge_user` had to be rewritten in `b4bdcec` because tests were leaking. Application has no equivalent janitor.
- **Consequence:** deleting a user from SQL fails or leaves embeddings/themes; `iris_test_db` already shows orphan-ish leftovers (27 embeddings with 0 journal_entries at first inspection).
- **Confidence:** Verified
- **Recommended verification:** `DELETE FROM users WHERE id=?` on a fixture user; observe FK errors / leftover embeddings.

### A-R-06 — IVFFlat indexes created on empty tables
- **Category:** Runtime search quality
- **Severity:** Medium
- **Evidence:** `create_schema` `CREATE INDEX IF NOT EXISTS idx_embeddings_vector_cosine ... ivfflat ... lists=100` (`database.py` 196–201) and themes lists=50. Live `iris_db` has those indexes with **2** embedding rows. pgvector docs (QueryPlane / pgvector README practice, verification 2026-09-06): IVFFlat k-means on empty/tiny tables yields a useless index; recommended lists ≈ rows/1000.
- **Explanation:** planner may still seq-scan at n=2; as data grows, un-rebuilt IVFFlat recall collapses.
- **Consequence:** “relevant long-term memory” in chat is wrong or empty without an obvious error (`search_similar_embeddings` catches exceptions and returns `[]` — `database.py` 731–733).
- **Confidence:** Inferred (index exists; query plan not EXPLAINed)
- **Recommended verification:** `EXPLAIN` a `<=>` query; rebuild IVFFlat after load or switch HNSW.

### A-R-07 — Tests can spend paid OpenAI budget and are not isolated
- **Category:** Test quality / cost / data
- **Severity:** High
- **Evidence:** `test_live_system.py` lines 20–57; `test_system_health_invariant.py` unmocked `create_reflection` → pipeline; `live_runner.py` prints `API key: {key[:8]}...` (key prefix leakage). Several API tests unmocked. Health-invariant does not use `test_user` purge. conftest **does** refuse non-`test` DB names (`conftest.py` 78–84) — good.
- **Explanation:** `pytest` with a real `.env` key bills embeddings for every habit/journal API test and the invariant test.
- **Consequence:** surprise API cost; pollution of `iris_test_db`; `live_runner` logs key prefixes.
- **Confidence:** Verified
- **Recommended verification:** run suite with a dummy key (done); with real key under a billing alert (not done).

### A-R-08 — Default secrets in code and config
- **Category:** Insecure defaults
- **Severity:** Medium
- **Evidence:** `Settings.POSTGRES_PASSWORD` default `"testpassword"` (`config.py` 32); `OPENAI_API_KEY` default `"your_openai_api_key_here"`; API user password `"local"`; Dockerfile `COPY .env.example .env`. Compose requires `POSTGRES_PASSWORD` to be set (good: `:?` syntax).
- **Explanation:** app can boot against a weak DB password without a `.env`.
- **Consequence:** local-dev defaults copied into a deployed container.
- **Confidence:** Verified
- **Recommended verification:** start without `.env` and print `settings.sanitized_dict()`.

### A-R-09 — No CI/CD, no automated lint/type/test gate
- **Category:** Deployment / maintainability
- **Severity:** Medium
- **Evidence:** no `.github/`; ruff 1584 issues; mypy not run in CI; Docker broken (A-OD-02).
- **Explanation:** recovery commits claim pass counts that this environment cannot reproduce without paid APIs.
- **Consequence:** regressions (like `journals` NameError, gate order) land uncaught.
- **Confidence:** Verified
- **Recommended verification:** search `.github` (missing).

### A-R-10 — Naive vs aware datetime residual
- **Category:** Correctness / reliability
- **Severity:** Medium
- **Evidence:** commit `14a4b24` message: engines “still mix naive and aware”. Code: windows often `datetime.now()` naive (`trajectory.py` 81, `tension.py` 54, `leverage.py` 78); occurrence timestamps stripped with `replace(tzinfo=None)` in some loops (drops offset rather than converting). `insights_service` uses `datetime.now(UTC)` and compares `snoozed_until` (timestamptz) to aware now (OK). `iris_api._age_days` strips tz then subtracts naive `datetime.now()` (line 721–723).
- **Explanation:** `replace(tzinfo=None)` on UTC timestamptz interprets local wall clock as UTC-naive — **window math can shift by the host offset** (this host is +0200).
- **Consequence:** trajectory/resolution “recent 14/21 days” mis-bucket around DST/offset; intermittent TypeError if a path forgets to strip (tests hit this before `14a4b24`).
- **Confidence:** Verified (stripping strategy); impact magnitude Inferred
- **Recommended verification:** store an occurrence at UTC midnight, run engines on a +0200 host, check `recent_count`.

### A-R-11 — Connection pool maxconn=5 plus per-request companion
- **Category:** Reliability
- **Severity:** Medium
- **Evidence:** `ThreadedConnectionPool(minconn=1, maxconn=5)` (`database.py` 55–56). Each HTTP chat constructs `PersonalAICompanion` (engines, prefs, pipeline) and `get_connection()` legacy conn is separate (`database.py` 104–120). FastAPI threadpool for LLM.
- **Explanation:** small pool; chat holds connections during OpenAI calls if a caller uses the legacy connection.
- **Consequence:** `PoolError` under a handful of concurrent tabs; not visible in tests (serial).
- **Confidence:** Inferred
- **Recommended verification:** 8 parallel `/messages/stream` requests.

### A-R-12 — Insight suggestion accept is a silent no-op
- **Category:** Misleading UX
- **Severity:** Low
- **Evidence:** `iris_api.py` 926–930 returns 204; comment “No server-side action wired”. Frontend `acceptSuggestion` exists.
- **Explanation:** user can “accept” a suggestion with no effect.
- **Confidence:** Verified
- **Recommended verification:** POST accept URL from an insight detail.

### A-R-13 — Companion logger format strings corrupted to `\1`
- **Category:** Observability
- **Severity:** Low
- **Evidence:** `companion.py` 24 occurrences of `logger.error(f"\1: {e}")` (e.g. lines 125, 147, 809). Clearly a botched regex replacement of a capture group.
- **Explanation:** CLI errors log as `\1: <exception>` without the intended prefix.
- **Consequence:** harder incident response; not a data-loss bug.
- **Confidence:** Verified
- **Recommended verification:** trigger CLI error, read `logs/iris_errors.log`.

### A-R-14 — Review letter and greeting always call the LLM; no offline mode
- **Category:** Reliability / privacy
- **Severity:** Medium
- **Evidence:** `_generate_review_letter` (`iris_api.py` 1035–1062) instantiates Intelligence; greeting/proactive/chat all need a non-placeholder key (`intelligence.py` 41–81 raises if both keys missing). Embeddings required for journal/habit ingest.
- **Explanation:** local-first is **data** local, not **compute** local. No local model path despite CONTEXT “LLM Provider … local”.
- **Consequence:** app is non-functional without a cloud key; all source text is sent to OpenAI for embeddings and chat.
- **Confidence:** Verified
- **Recommended verification:** empty OpenAI key, POST `/api/journal`.

### A-R-15 — Theme delete does not remove embeddings or insight_status
- **Category:** Privacy / data leftover
- **Severity:** Medium
- **Evidence:** `DELETE /api/knowledge/{id}` → `db.delete_theme` (theme row + cascaded occurrences). Embeddings for the underlying reflections remain. `insight_status` rows keyed by `trajectory:theme_id` etc. are not cleaned.
- **Explanation:** “forget this fact” is incomplete.
- **Consequence:** semantic search can still retrieve forgotten content; snooze table retains ids.
- **Confidence:** Verified
- **Recommended verification:** create theme-backed knowledge, DELETE, search embeddings by source.

### A-R-16 — Dockerfile copies `.env.example` into the image as `.env`
- **Category:** Container secrets
- **Severity:** Medium
- **Evidence:** `Dockerfile` line 26 `COPY .env.example .env`. `.dockerignore` excludes `.env` (good) but the example file still becomes the process env inside the image. Compose also `env_file: .env`.
- **Explanation:** image contains placeholder keys; compose overrides at runtime if `.env` exists.
- **Consequence:** running the image without compose uses placeholders; accidental commit of a filled example would bake secrets (current example is placeholders).
- **Confidence:** Verified
- **Recommended verification:** `docker history` / inspect once docker works.

---

## 8. Unknowns and unresolved questions

1. **Would the full suite pass with the live OpenAI key?** Commit `14a4b24` says 134/134. This audit reproduced 132 pass + 1 fail (health invariant, dummy key) + 1 skipped live test. **Unknown** without spending budget.
2. **Theme discovery quality without hdbscan.** Fallback is sklearn DBSCAN; clustering metric/params not compared. Unverified on real embeddings.
3. **IVFFlat query plans** on PG 18.6 with n=2 and lists=100. Not EXPLAINed.
4. **Docker image build** — blocked by socket permissions.
5. **Production SPA build freshness** — `frontend/dist` exists (mtime 2026-09-06 09:39) but `npm run build` was not run (would write the repo). Whether dist matches `src/` is **unknown**.
6. **Content of the 2 live `iris_db` messages** — not read (privacy). Whether they already have message-typed `theme_occurrences` from before `14a4b24` is unknown (`theme_occurrences` count was 0).
7. **Whether `iris_rails_*` databases interact with this app** — names suggest a different project on the same cluster. Unverified.
8. **Gemini provider** — never exercised (`use_gemini` false; SDK EOL).
9. **Habit skip → theme occurrence** — skips call `run_processing_pipeline('habit_completion', ...)`. Whether skipped days become evidence is unverified.
10. **Timezone bucket shift (+0200)** magnitude on resolution labels — inferred, not measured.
11. **Concurrent pipeline corruption (A-R-02)** — reasoned from code, not race-tested.
12. **Official gpt-4.1-mini availability on this account** — model exists in OpenAI docs (2026-09-06); whether this API key can call it was not tested.

---

## 9. Prioritized recovery recommendations (do not implement here)

1. **Unblock deploy docs and containers (Critical).** Replace Dockerfile with uv + `frontend/dist` (or multi-stage Node build); delete Poetry/`iris_frontend.html` references; make README match single-user loopback + native Postgres. Do not recommend compose until the image builds.
2. **Fix pipeline identity (Critical).** `get_items_to_process` must load **the given `source_id`**, not `LIMIT 1` by status. Then remove the duplicate BackgroundTask on `/api/reflections`.
3. **Close the message-as-evidence hole completely (High).** Exclude `message` (and probably `habit` definitions) from `get_unassigned_embeddings` / `discover_themes`, matching `14a4b24` and CONTEXT.md.
4. **Pick one journal model (High).** Either map the SPA onto `journal_entries` or delete/rename the unused table and CONTEXT “Journal Entry” to Reflection. Fix `JournalEntry`’s missing `journals` import or delete the CLI path.
5. **Make failures visible (High).** Do not return 200 when embeddings fail; do not persist `"Error calling API"` as Iris. Surface processing_status in the UI.
6. **Authz/bind defaults (High).** Keep loopback as the only documented bind; refuse `0.0.0.0` unless an explicit flag is set. Replace SHA-256 with a KDF if any password remains. Rotate the default `"local"` password.
7. **Stop lying in the SPA (High).** Honor `VITE_USE_MOCKS` globally or not at all; Body/Today must use `/api/body/source` when mocks are off; hide Fitbit copy; wire or remove connector/onboarding/forget/export buttons.
8. **Align meta-control with CONTEXT.md (High).** Gate order: enablement → confidence → conflict → rank → budget (once). Register conflict as an orchestrator gate or remove budget from the orchestrator.
9. **Test hygiene (High).** Mock embeddings in **all** default tests; mark live tests; force every test through `test_user` purge; never print API key prefixes. Add a CI workflow that runs the dummy-key suite on `iris_test_db`.
10. **Schema as migrations (High).** Introduce numbered migrations (even a simple SQL dir): CASCADE on user-owned tables, embedding FKs or at least user_id, HNSW or deferred IVFFlat. Do not rely on `CREATE IF NOT EXISTS`.
11. **Unify model config (Medium).** `PersonalAICompanion` and review letter should read `settings.OPENAI_MODEL`. Drop or migrate `google-generativeai`.
12. **Timezones (Medium).** Store and compare in UTC aware datetimes; never `replace(tzinfo=None)` on timestamptz.
13. **Delete or quarantine dead code (Low/Medium).** `engine_base.py`, `narrative_system.py`, archive HTML warnings, `/rebuild-vector` help, `CHROMADB_TELEMETRY`, Neo4j env keys, companion `\1` log format.
14. **Privacy “forget” (Medium).** DELETE knowledge must delete embeddings + insight_status + occurrences; implement the Settings handlers that the copy already describes.
15. **Do not treat 132/133 dummy-key pytest as product certification.** The interesting ingest→theme→chat path is exactly what the green API tests do not assert.

---

## 10. Audit coverage and limitations

**Covered:** git snapshot identity; tree inventory; pyproject/lock/venv; config/env **keys**; FastAPI route table; schema + FK + row counts on `iris_db` and `iris_test_db`; engine/pipeline/core/insights/frontend contracts; commit history 2026-01-05 → 2026-09-06; pytest on dedicated test DB with invalid OpenAI key; frontend `tsc --noEmit`; ruff volume; compileall; official docs for google-generativeai EOL, gpt-4.1-mini existence, IVFFlat-empty-table practice, FastAPI/Starlette 1.x compatibility (2026-09-06).

**Not covered / blocked:** docker build and compose; live OpenAI chat/embeddings; browser E2E; production `vite build`; load/race tests; reading user message bodies; other auditors’ reports (explicitly unread, including files that happened to exist under `/tmp/iris-audit-2026-09-06/` besides this report).

**Independence:** no files under `/home/noodis/.claude/plans/` were read. Prior session histories were not read. README/ARCHITECTURE were treated as claims and checked against code.

**Mutations:** none inside `/home/noodis/Iris-01`. Allowed test-DB writes occurred via pytest against `iris_test_db` only. `iris_db` was inspected read-only.

**Working tree at end of investigation:**

```
# git status --porcelain
(empty)
```

`git status` reported: `On branch recovery/2026-09-06-baseline`, `nothing to commit, working tree clean`. HEAD still `14a4b242ae908c36b6a9ecf72ed9f1e5b39bfac3`.

---

## Finding index (severity)

| ID | Sev | One-line |
|---|---|---|
| A-OD-02 | Critical | Dockerfile needs missing Poetry lock + deleted HTML |
| A-R-01 | Critical | No auth; Docker/README bind 0.0.0.0 |
| A-R-02 | Critical | Pipeline embeds the wrong row under concurrency |
| A-OD-01 | High | README/ARCHITECTURE describe Vanilla JS + Chroma + multi-user |
| A-OD-04 | High | setup_db.sh / systemd target wrong names and paths |
| A-OD-05 | High | Unsalted SHA-256 passwords |
| A-LI-01 | High | SPA journal ≠ `journal_entries` |
| A-LI-02 | High | Discovery can still theme-cluster chat messages |
| A-LI-03 | High | Budget-before-rank vs CONTEXT gate order |
| A-LI-05 | High | Body UI mocks vs missing overview API |
| A-LI-07 | High | `journals` NameError on CLI journal |
| A-LI-08 | High | Causal insights + un-firewalled LLM vs contract |
| A-R-03 | High | Swallowed embedding/LLM errors; tests stay green |
| A-R-04 | High | No real migrations |
| A-R-05 | High | Missing CASCADE / embedding FKs |
| A-R-07 | High | Default pytest can bill OpenAI; leaky tests |
| A-OD-03 | Medium | google-generativeai EOL |
| A-OD-07 | Medium | Tooling py314 vs runtime 3.11.9 |
| A-OD-08 | Medium | PG16 compose vs PG18 host; leftover Neo4j env |
| A-LI-04 | Medium | CLI multi-user vs API single-user |
| A-LI-06 | Medium | gpt-4.1-mini vs gpt-4o-mini vs settings |
| A-LI-10 | Medium | Onboarding API unused by UI |
| A-LI-11 | Medium | Fake connectors |
| A-LI-13 | Medium | Two preference stores |
| A-LI-16 | Medium | Double pipeline on reflections POST |
| A-LI-17 | Medium | Fake SSE streaming |
| A-LI-18 | Medium | Port 5432/5433 and 8000/8080 mismatch |
| A-LI-19 | Medium | Forget/export/delete buttons dead |
| A-R-06 | Medium | IVFFlat on empty tables |
| A-R-08 | Medium | Default DB/API passwords in code |
| A-R-09 | Medium | No CI |
| A-R-10 | Medium | Naive timestamptz stripping |
| A-R-11 | Medium | Pool maxconn=5 |
| A-R-14 | Medium | Cloud LLM required despite “local-first” |
| A-R-15 | Medium | Forget does not delete embeddings |
| A-R-16 | Medium | Image copies `.env.example` to `.env` |
| A-OD-06 | Low | pydantic `.dict()` |
| A-OD-09 | Low | Missing `docs/adr/` |
| A-OD-10 | Low | Archive points at deleted Vanilla JS |
| A-LI-09 | Low | NARRATIVE_FAIL_MODE env ignored |
| A-LI-12 | Low | Habit color not persisted |
| A-LI-14 | Low | `/rebuild-vector` help only |
| A-LI-15 | Low | Unused engine_base/narrative_system |
| A-R-12 | Low | Suggestion accept no-op |
| A-R-13 | Low | companion.py `logger.error(f"\1: {e}")` |

**Counts:** Critical 3 · High 13 · Medium 20 · Low 9 · **Total 45**


# Part 3 — Auditor B (R2) complete report

# IRIS Ground-Zero Audit Report — Auditor B

- **Auditor identity:** Auditor B (secondary lens: adversarial system-consistency; full-project scope)
- **Repository:** `/home/noodis/Iris-01`
- **Snapshot branch:** `recovery/2026-09-06-baseline`
- **Snapshot commit:** `14a4b242ae908c36b6a9ecf72ed9f1e5b39bfac3`
- **Commit subject:** `fix: stop counting chat messages as theme occurrences`
- **Investigation start:** 2026-09-06T09:10:16Z
- **Investigation end:** 2026-09-06T09:19:41Z
- **Working tree at start:** clean
- **Working tree at end:** unmodified (`git status --porcelain` empty)
- **Host date:** 2026-09-06
- **Host `python3`:** 3.14.7
- **`.python-version`:** 3.11.9
- **`.venv` interpreter:** Python 3.11.9
- **Package manager:** uv 0.12.9
- **Docker CLI:** Docker 29.7.2
- **PostgreSQL (host):** 18.6 (Debian), `pgvector` extension 0.8.6
- **Node:** v26.8.1 / npm 11.19.0

Snapshot confirmation (read-only git): branch, commit, and subject match the assigned snapshot. No files were written inside the repository. The only file written by this audit is this report.

---

## 1. Executive summary

IRIS is a local-first personal companion that is supposed to observe journal/reflection/habit evidence, compute deterministic pattern insights, and talk about those observations without inventing causality. The checked-out tree is a **mid-refactor recovery snapshot**, not a finished product. On 2026-09-06 the branch removed Neo4j, removed the HTTP auth/CORS surface, pointed tests at a dedicated database, and stopped treating chat messages as theme occurrences. Those commits sit on top of a 2026-06-14 “working state” snapshot (`70bf1d2`) and a much older documentation/deployment story.

**What actually exists:** a FastAPI process (`iris_api.py`) wrapping `PersonalAICompanion`, a PostgreSQL+pgvector schema created in-process by `Database.create_schema()`, a React+Vite SPA under `frontend/`, a still-multi-user CLI (`companion.py`), and a large pytest suite that talks to Postgres.

**What does not exist, despite docs and Docker files:** Vanilla JS `iris_frontend.html`, ChromaDB/FAISS, Neo4j, Poetry `poetry.lock`, GitHub Actions, `docs/adr/`, versioned SQL migrations, wearable/OAuth backends, and a working container build.

The system is **not deployment-ready** and is only **partially usable as a local product**. The analytical engines are real, but the primary UI workflow cannot form new themes: HTTP journal writes go to `reflections`, not `journal_entries`, and `PersistenceEngine.discover_themes()` is CLI-only. The ingest pipeline fetches “an item with this status” rather than “this source_id”, which this audit reproduced as a failing test (`test_complete_journal_entry_flow`). Frontend local config has `VITE_USE_MOCKS=true`, so a developer can believe the product works while talking to in-memory Fitbit/journal fixtures. Docker cannot build. README still describes a different architecture.

**Readiness judgment:** not ready for production, not ready for multi-user use, and not a reliable single-user companion until ingest, discovery, docs, and deploy artifacts are reconciled.

**Finding severity counts:** Critical 5 · High 13 · Medium 19 · Low 5 · Total 42

---

## 2. Reconstructed project purpose and architecture

### Intended purpose (from code + domain docs, not from README alone)

IRIS (“The Epistemic Mirror”) is a **personal, local-first AI companion**. Intended user: a single person running the app against their own Postgres and an LLM API key. The non-interpretive contract, stated in `CONTEXT.md` and `prompts/system_prompt.py` with different strictness, is: observe and report evidence; do not assign causality or unsolicited advice.

Promised capabilities:

- Capture journal-like text, reflections (mood/energy/clarity), and habits.
- Embed content (`text-embedding-3-small`, 1536-d) into PostgreSQL `vector` columns.
- Cluster/match **themes**, then run trajectory, tension, resolution, leverage, and decision-impact engines.
- Gate insights (enablement → confidence → conflict → priority → budget) and render them through a narrative firewall.
- Chat with an LLM that is injected with those narratives plus recent habits/reflections/memories.
- A web UI for chat, today, journal, habits, insights, review, body, settings, onboarding.

### Architecture that the *code* implements

```
Vite SPA (frontend/src)  --/api-->  FastAPI (iris_api.py)
                                      |  get_current_user_id()
                                      |  lazily creates users.username=IRIS_DEFAULT_USER
                                      v
                              PersonalAICompanion (agent/core.py)
                                      |
          +---------------------------+---------------------------+
          |                           |                           |
   ConversationMemory           AnalysisPipeline            Intelligence
   JournalEntry (CLI path)      engines + gates             OpenAI primary
   HabitTracker / ReflectionService                         Gemini fallback (dead SDK)
          |                           |
          v                           v
   PostgreSQL + pgvector (canonical store; no second database in this snapshot)
```

Startup path:

1. `python iris_api.py` → `uvicorn.run(app, host="127.0.0.1", port=8000)`.
2. FastAPI lifespan calls `db.create_schema()` (idempotent `CREATE TABLE IF NOT EXISTS` + a few `ALTER … ADD COLUMN IF NOT EXISTS`).
3. If `frontend/dist/index.html` exists, `/` and `/{full_path:path}` serve the SPA.
4. Alternate entry: CLI `companion.py` (login/create-user loop) or console script `iris = "companion:main"` in `pyproject.toml`.
5. Docker intended path: `docker-compose.yml` starts `pgvector/pgvector:pg16` on host port 5433 and an `agent` image on 8000. That image cannot be built from this tree (see B-OD-01).

### Decisions that changed and were not fully propagated

Evidence is the commit history (26 commits total) plus leftover files:

| Decision | When | Propagated to | Not propagated to |
|---|---|---|---|
| Poetry → uv | `ce30b11` 2026-05-17 | `pyproject.toml`, `uv.lock`, `.venv` | `Dockerfile` (`poetry.lock`, `poetry install`), `COMPATIBILITY_REPORT.md` |
| FAISS/Chroma → pgvector | `e387b5c` 2026-01-25 | `agent/database.py`, tests | `README.md`, `ARCHITECTURE.md`, `.env.example` (`ANONYMIZED_TELEMETRY` / Chroma), `agent/config.py` `CHROMADB_TELEMETRY` |
| Neo4j added then removed | `a4b6d4d` then `c591509` 2026-09-06 | source deleted (`agent/graph_db.py` gone) | `.env` still has `NEO4J_*`; `__pycache__/graph_db.cpython-*.pyc` remains; tests still comment “Mock graph operations” |
| Multi-user HTTP auth → single-user no auth | `9d97803` 2026-09-06 | `iris_api.py` `get_current_user_id` | `README.md` (“Multi-user HTTP Gateway”), `companion.py` login/create-user, SHA256 `users.password_hash`, archive frontend JWT docs |
| Vanilla JS frontend → React SPA | SPA added under `frontend/`; Vanilla files deleted in recovery diff (`iris_frontend.html` −837 lines) | `iris_api.py` serves `frontend/dist` | `README.md`, `ARCHITECTURE.md`, `Dockerfile` `COPY iris_frontend.html`, `archive/iris-frontend-react/README.md` |
| Chat messages are not occurrences | `14a4b24` (HEAD) | `agent/pipeline.py` `should_check_persistence` | `PersistenceEngine.discover_themes()` / `get_unassigned_embeddings()` still include `message`; `persistence.py` docstring still says conversations |
| Frontend journal contract | API tests + `iris_api.py` map journal → reflections | `frontend/src/api/journal.ts`, `/api/journal` | `journal_entries` table, CLI `/journal`, `core._get_recent_journal_entries_context()`, almost all engine tests |

This is a **partial replacement**, not a completed migration. The HEAD commit message itself refers to “the timezone finding in the audit” and queues “M3.3”, i.e. this snapshot is already inside a remediation sequence.

### Original vs current intended features

- **Original (Jan 2026):** CLI analytical core, journal entries, theme engines, later a multi-user API and Vanilla JS UI.
- **Current intended (code + frontend types):** single-user local SPA covering chat, journal, habits, insights, weekly review, settings/connectors, onboarding, and a body/wearable pane. Several of those screens are marked PARTIAL in `frontend/README.md` and are either unwired (onboarding UI, body overview API, mobile) or honest stubs (`GET /api/body/source` returns `kind: none`).

---

## 3. Current-state component map

### Runtimes and toolchains

| Layer | Declared | Actual on this host |
|---|---|---|
| Python | `.python-version` 3.11.9; `requires-python = ">=3.11,<3.15"`; Black/mypy target **3.14** | Host 3.14.7; project `.venv` 3.11.9 |
| Packaging | uv (`uv.lock`); hatch wheel `packages = ["agent"]` | Dockerfile still Poetry |
| Frontend | React 18.3, Vite 5.4, TypeScript, TanStack Query, Zustand, React Router 6 | `frontend/node_modules` present; `tsc --noEmit` passes |
| DB | Postgres + pgvector; compose image `pgvector/pgvector:pg16` on port **5433** | Host Postgres **18.6** on **5432**; `.env` `POSTGRES_PORT=5432`; compose stack **not running** |
| LLM | OpenAI (`openai==2.37.0`), optional Gemini | `OPENAI_API_KEY` set (non-placeholder); Gemini uses EOL `google-generativeai==0.8.6` |

### Backend modules (`agent/`)

| Module | Responsibility | Notes |
|---|---|---|
| `database.py` | Singleton pool + schema + SQL | ~2500 lines; still the real data layer |
| `repositories.py` | Domain facades over `db` | Stale `HabitRepository.create_habit` signature |
| `pipeline.py` | Embed + optional persistence match | Does not discover new themes; item fetch unscoped |
| `pipeline_orchestrator.py` | Engine registry + enablement/confidence/budget gates | Conflict/priority happen later in `core.py` |
| `persistence.py` / `trajectory.py` / `tension.py` / `resolution.py` / `leverage.py` / `decision_impact.py` | Analytical engines | Do **not** inherit unused `engine_base.py` |
| `conflict.py` + `conflicts.py` | Conflict suppression | Used from `core.py`, not registered as a pipeline gate |
| `narrative.py` + `narrative_policy.py` + `narrative_templates.py` | Firewall | Parallel unused `narrative_system.py` |
| `insights_service.py` | Engine output → frontend InsightSummary/Detail | Maps leverage/decision_impact to `kind: "causal"` |
| `core.py` | Chat orchestration | Default model `gpt-4.1-mini` (not `settings.OPENAI_MODEL`) |
| `intelligence.py` / `llm_provider.py` | LLM adapters | Error strings returned as “assistant” text |
| `memory.py` | Chat persistence + pipeline | New `session_id` per `PersonalAICompanion()` instance |
| `journal_entry.py` | CLI journal → `journal_entries` | `journals` used but not imported (NameError) |
| `trackers/habits.py`, `trackers/reflections.py` | HTTP-facing services | Reflections are the web journal store |
| `config.py` | pydantic-settings | Defaults include `POSTGRES_PASSWORD=testpassword` |
| `engine_base.py`, `narrative_system.py` | Dead seams | No production importers |

### HTTP API (`iris_api.py`)

Single-user seam: `DEFAULT_USERNAME`/`DEFAULT_PASSWORD` from `IRIS_DEFAULT_USER`/`IRIS_DEFAULT_PASSWORD` (default `"local"`/`"local"`). No cookies, no bearer, no CSRF. Every route that `Depends(get_current_user_id)` is the same user.

Implemented (non-exhaustive): `/health`, chat greeting/proactive, conversations current/messages/inferred/stream, habits CRUD + today/toggle/complete/skip/calendar, reflections CRUD, journal GET/POST (reflection mapping), user/preferences, knowledge, connectors, onboarding, insights list/detail/snooze/resolve/accept, review latest/week, body source, SPA fallback.

**Missing relative to `frontend/src/types/api.ts` and `frontend/src/api/body.ts`:** `GET /api/body/overview`, `GET /api/body/day/:date`.

### Frontend

- Production-shaped app: `frontend/src/` (React).
- Design prototype (visual source of truth per frontend README): `frontend/design-prototype/` (not repo-root `index.html` as that README claims).
- Archived React app: `archive/iris-frontend-react/` (docs still say Vanilla JS is production).
- Local `frontend/.env.local`: `VITE_USE_MOCKS=true`, empty `VITE_BACKEND_URL`.
- Untracked `frontend/dist/` is served by FastAPI when present; bundle contains `Fitbit Air` mock copy.

### Data stores

- Canonical: PostgreSQL databases `iris_db` (app) and `iris_test_db` (tests). Both exist on localhost:5432.
- No Chroma, no FAISS, no Neo4j process required by current code.
- Schema is code-defined, not Alembic. Several tables lack `ON DELETE CASCADE` from `users` (`journal_entries`, `conversation_messages`, `themes`, `embeddings` have no user FK at all).
- At audit time, **application** `iris_db` had 1 user, 0 journals, 0 reflections, 2 messages, 0 habits (counts only; no content inspected). **Test** `iris_test_db` still held 14 users, 45 reflections, 41 embeddings after the suite — purge is incomplete for historical rows.

### Tests / CI / deploy

- `tests/` ~40 modules, 134 collected tests. No `@pytest.mark.skip`. `tests/test_live_system.py` calls the real OpenAI API and is in the default collection.
- No `.github/` workflows.
- `Dockerfile` + `docker-compose.yml` + `scripts/iris.service.example` + `scripts/setup_db.sh` are all stale relative to uv/single-user/pgvector-on-5432.

### Incomplete / abandoned / duplicated

- `journal-upgrade` (UTF-8 text blob at repo root; not referenced).
- `23.01.2026.md` (unrelated `/etc/hosts` notes).
- `COMPATIBILITY_REPORT.md` (Poetry + Python 3.14.2).
- `q` deleted in recovery diff (969 lines) — leftover name from an earlier dump.
- Duplicate narrative/conflict/engine abstractions (`narrative_system.py`, `engine_base.py`).
- Two frontends + a prototype + an archive.
- CLI vs HTTP as two products sharing engines.

---

## 4. Validation commands and results

All commands used `/home/noodis/Iris-01/.venv/bin/python` unless noted. Tests were aimed at `iris_test_db` via `tests/conftest.py` (`POSTGRES_DB` forced to `iris_test_db` / `IRIS_TEST_POSTGRES_DB`, refuse unless `"test"` in the name). Application database `iris_db` was not written by this audit except that pytest did **not** target it. `test_live_system.py` was excluded to avoid an intentional paid live run; several API tests still *can* call embeddings (see B-R-06).

### 4.1 Snapshot / environment

| Check | Command / method | Result |
|---|---|---|
| Branch/commit | `git rev-parse --abbrev-ref HEAD`; `git rev-parse HEAD` | `recovery/2026-09-06-baseline` / `14a4b242ae908c36b6a9ecf72ed9f1e5b39bfac3` |
| Working tree | `git status --porcelain` (start and end) | Empty |
| Runtimes | `python3 --version`; `.venv/bin/python --version`; `uv --version`; `docker --version` | 3.14.7 / 3.11.9 / uv 0.12.9 / Docker 29.7.2 |

### 4.2 Syntax / import

| Check | Command | Result | Cause / leftover unverified |
|---|---|---|---|
| Bytecode compile | `.venv/bin/python -m compileall -q agent iris_api.py companion.py prompts` | Exit 0 | Does not prove runtime |
| Import API | import `iris_api` with `POSTGRES_DB=iris_test_db` (no lifespan/schema write in that process) | `COMPANION_AVAILABLE True`; 53 routes; `frontend/dist` present | Lifespan `create_schema()` not exercised in this import |
| `journal_entry.py` | mypy + source read | `Name "journals" is not defined` at `JournalEntry.create_entry` | CLI `/journal` is broken; not executed (would hit DB + OpenAI) |

### 4.3 Tests

| Check | Command | Result |
|---|---|---|
| Collection | `.venv/bin/python -m pytest --collect-only -q` | **134 tests collected** in 0.43s, including `tests/test_live_system.py` |
| Suite excluding live | `.venv/bin/python -m pytest tests/ --ignore=tests/test_live_system.py --ignore=tests/live_runner.py -q --tb=line` | **1 failed, 132 passed in 31.99s** |

**Failure (verbatim assertion):**

`tests/test_end_to_end.py::test_complete_journal_entry_flow`  
`AssertionError: assert 'Stress 0' == 'Today I had an important realization:\n- Work-life balance is crucial\n- Self-care matters'`

The test creates a journal row, then calls `db.get_items_to_process('journal_entry', status='pending', limit=1)` **without a source_id or user_id** and expects that row. It received leftover `'Stress 0'` content (the fixture pattern used by stress/regression tests). This is both a product bug (unscoped fetch) and a test-isolation bug (`iris_test_db` retained 14 users / 45 reflections / 41 embeddings after the run).

HEAD commit message claims “Full suite: 134 passed, 0 failed”. That claim is **false in this environment**.

Live test: **not run** (`tests/test_live_system.py` docstring: “Uses real OpenAI API for embeddings and chat”). `tests/run_live_test.sh` exports `OPENAI_API_KEY` from `.env`.

### 4.4 Lint / types

| Check | Command | Result |
|---|---|---|
| Ruff | `.venv/bin/ruff check agent iris_api.py companion.py` | **1584 errors**, 872 auto-fixable. `pyproject.toml` selects a very large rule set (`E,W,F,I,B,C4,C9,DTZ,…`). Not a clean project under its own config. |
| Mypy | `.venv/bin/mypy agent iris_api.py companion.py` | **410 errors in 31 files** (checked 39). Includes the `journals` NameError. `pyproject.toml` sets `python_version = "3.14"` while the venv is 3.11.9. |
| Frontend types | `cd frontend && npx tsc --noEmit` | **Exit 0** |

### 4.5 Frontend production build

**Not run.** `npm run build` writes `frontend/dist/` and `*.tsbuildinfo` inside the repository. Diagnostic rules forbid writing repo files. Existing untracked `frontend/dist/` was inspected read-only.

### 4.6 Docker / compose

| Check | Command | Result |
|---|---|---|
| Compose file validity | `docker compose config -q` | Exit 0 (uses `.env` `POSTGRES_PASSWORD`) |
| Compose stack | `docker ps` | **No containers**. Port 5433: `pg_isready` “no response”. Port 5432: accepting |
| Image build | Inspected `Dockerfile`; did **not** build | `COPY poetry.lock` and `COPY iris_frontend.html` — **both missing**. Build would fail. Not “usable without compose”. |

### 4.7 Database

| Check | Result |
|---|---|
| `pg_isready -h localhost -p 5432` | accepting connections |
| `pg_isready -h localhost -p 5433` | no response (compose mapping unused) |
| Databases | `iris_db`, `iris_test_db`, plus unrelated `iris_rails_*` |
| Schema strategy | `CREATE TABLE IF NOT EXISTS` in `Database.create_schema()`; no Alembic, `scripts/setup_db.sh` comments out `scripts/schema.sql` (file absent) |

Application startup against `iris_db` was **not** performed (`iris_api.py` lifespan would `create_schema()` on the user database). Health-check-only startup without lifespan is not how uvicorn serves the app.

### 4.8 Dependency resolution

Lockfile `uv.lock` is present and matches installed `.venv` versions sampled (`fastapi==0.136.1`, `openai==2.37.0`, `google-generativeai==0.8.6`, `numpy==2.4.5`, `scikit-learn==1.8.0`, `pytest==9.0.3`). `uv lock` / `uv sync` were **not** run (mutating).

### 4.9 What passing tests do *not* prove

- They do not prove theme formation from the SPA journal path (tests seed `journal_entries` or insert themes directly; web journal uses reflections).
- `tests/test_user_gates.py` and `tests/test_user_control.py` reimplement gate logic inline (`filtered = [i for i in raw if …]`) instead of calling `AnalysisPipeline.run()` / `_get_aggregated_context()`. `test_suppression_buffer_populated` is `pass`.
- API chat/journal/review tests mock `Intelligence` (sometimes) but `ReflectionService.create_reflection` / `HabitTracker.log_completion` still call `run_processing_pipeline` → `generate_embedding`. Those tests can bill OpenAI and still pass if the pipeline exception is swallowed.
- Insights tests seed a theme + occurrences; they do not run discovery.
- HEAD’s “134 passed” is already stale.

---

## 5. Outdated-items register

Outdated here means **broken compatibility, EOL, or instructions that cannot be followed**, not “a newer version exists”.

### B-OD-01 — Dockerfile references deleted Poetry frontend stack

- **Category:** Outdated / deploy
- **Severity:** Critical
- **Evidence:** `Dockerfile` lines 16–26: `COPY pyproject.toml poetry.lock ./`, `RUN pip install --no-cache-dir poetry` + `poetry install --only=main`, `COPY iris_frontend.html .`. `git ls-files` has no `poetry.lock` or `iris_frontend.html`. Recovery diff `70bf1d2..HEAD` deletes `iris_frontend.html` (837 lines). Compose `agent.build.target: runtime` uses this Dockerfile.
- **Explanation:** The recommended deploy path in `README.md` (`docker-compose up --build -d`) cannot produce an image from this commit.
- **Consequence:** Anyone following README fails at build; production containerization is fiction.
- **Confidence:** Verified
- **Recommended verification:** `docker build .` once writing/network is allowed; expect COPY failure.

### B-OD-02 — README / ARCHITECTURE describe a different product

- **Category:** Outdated docs
- **Severity:** High
- **Evidence:** `README.md` lines 3, 29–32, 44–48 (“Vanilla JavaScript”, “Vector DB: ChromaDB / FAISS”, “Multi-user HTTP Gateway”, docker-compose). `ARCHITECTURE.md` lines 15–19 (ChromaDB/FAISS, Vanilla JS, “multi-stage Docker builds”). Code: React SPA, pgvector only, `9d97803` “single-user, no auth”, Dockerfile is **not** multi-stage (single `FROM python:3.11-slim AS runtime`).
- **Explanation:** Root docs were not updated through the 2026-09-06 monolith recovery.
- **Consequence:** Operators and future agents will restore the wrong stack (Poetry, Chroma, Vanilla file, auth, port 5433).
- **Confidence:** Verified
- **Recommended verification:** Diff README against `iris_api.py` `/` handler and `frontend/package.json`.

### B-OD-03 — `google-generativeai` SDK is end-of-life

- **Category:** Outdated dependency
- **Severity:** High
- **Evidence:** `pyproject.toml` line 13 `google-generativeai>=0.8.0`; lock/venv `google-generativeai==0.8.6`. `agent/intelligence.py` lines 16–20 import it and suppress `FutureWarning`. Official: GitHub `google-gemini/deprecated-generative-ai-python` archived **2025-12-16**; README EOL **2025-11-30**; replacement `google-genai` (`https://github.com/googleapis/python-genai`, release 2.22.0 dated 2026-09-02). Google AI for Developers libraries page: legacy `google-generativeai` “Not actively maintained”. Verification date **2026-09-06**.
- **Explanation:** Gemini fallback cannot be maintained; new Gemini models/APIs will not appear on this SDK.
- **Consequence:** Fallback path is a ticking break; import already warns. Not the primary path if OpenAI is configured.
- **Confidence:** Verified (docs); runtime Gemini call unverified (no `GEMINI_API_KEY` exercised)
- **Recommended verification:** Call `Intelligence(use_gemini=True)` against Gemini 2.5/3.x and confirm API errors.

### B-OD-04 — Ops scripts and systemd unit target a previous app path and DB names

- **Category:** Outdated ops
- **Severity:** High
- **Evidence:** `scripts/setup_db.sh` creates user `iris_app` and database `iris_agent` on port **5432**; `.env.example` / compose / `settings` use `iris_user` / `iris_db` and document **5433**. `scripts/iris.service.example` `WorkingDirectory=/home/noodis/Myself/apps/personal_ai_agent_minimal`, `ExecStart=…/companion.py`. `docs/PGVECTOR_MIGRATION.md` lines 23–37: “Flask”, “psycopg3”, multi app-server diagram.
- **Explanation:** Leftovers from `personal_ai_agent_minimal` / distributed-vector-DB era.
- **Consequence:** Following `setup_db.sh` creates a database the app will not use; systemd will not start this tree.
- **Confidence:** Verified
- **Recommended verification:** Dry-run the shell script against the names in `.env.example`.

### B-OD-05 — Tooling Python version is internally inconsistent

- **Category:** Outdated / toolchain
- **Severity:** Medium
- **Evidence:** `.python-version` = `3.11.9`. `pyproject.toml` `[tool.black] target-version = ['py314']`, `[tool.mypy] python_version = "3.14"`. Host interpreter 3.14.7; `COMPATIBILITY_REPORT.md` says the system is on **3.14.2** and to use Poetry/pyenv 3.11. `requires-python = ">=3.11,<3.15"`.
- **Explanation:** Type-check/format config pretends the code is 3.14; runtime venv is 3.11.9. The compatibility report is a historical incident report, not current procedure.
- **Consequence:** Mypy 410 errors are partly config noise; a future `uv python` mix-up can re-break scientific wheels.
- **Confidence:** Verified
- **Recommended verification:** Run mypy with `--python-version 3.11` and compare error counts.

### B-OD-06 — Frontend example backend port and mock default

- **Category:** Outdated config
- **Severity:** Medium
- **Evidence:** `frontend/.env.example` `VITE_BACKEND_URL=http://localhost:8080` and `VITE_USE_MOCKS=true`. API listens on **8000** (`iris_api.py` `__main__`, compose `8000:8000`). `frontend/.env.local` has `VITE_USE_MOCKS=true` and empty `VITE_BACKEND_URL`.
- **Explanation:** Prototype-era port 8080; mock-on-by-default was never flipped when API modules were marked “WIRED LIVE”.
- **Consequence:** `npm run dev` without editing env talks to mocks (or proxies to the wrong port if URL is filled from the example).
- **Confidence:** Verified
- **Recommended verification:** Boot Vite with the example file unmodified and watch `/api` traffic.

### B-OD-07 — Compose Postgres 16 vs host Postgres 18; leftover Chroma flags

- **Category:** Outdated config
- **Severity:** Medium
- **Evidence:** `docker-compose.yml` `image: pgvector/pgvector:pg16`. Host DB is PostgreSQL **18.6**. `.env.example` line 29 `ANONYMIZED_TELEMETRY=False # Disable ChromaDB telemetry`. `agent/config.py` `CHROMADB_TELEMETRY`. `.env` still contains `NEO4J_URI=bolt://localhost:7688` (name only logged).
- **Explanation:** Vector-lens and graph-lens remnants after `e387b5c` and `c591509`.
- **Consequence:** Port/engine mismatch if someone starts compose against an already-running PG 18; dead env keys hide whether Neo4j is still expected.
- **Confidence:** Verified
- **Recommended verification:** `docker compose up postgres` (when allowed) and compare `server_version` to host.

### B-OD-08 — Pydantic v2 `.dict()` alias still used

- **Category:** Deprecated API
- **Severity:** Low
- **Evidence:** `iris_api.py` lines 455 and 612 `updates.dict(exclude_none=True)`. Pydantic v2 (installed 2.13.4) prefers `model_dump()`. Alias still works today.
- **Explanation:** Will break on a future Pydantic 3 removal.
- **Consequence:** Habit/reflection PUT would 500 after upgrade.
- **Confidence:** Verified (call sites); removal timeline Unknown
- **Recommended verification:** Pydantic deprecation warnings under `PYTHONWARNINGS=error`.

### B-OD-09 — No CI; hatch wheel omits the HTTP/CLI entrypoints

- **Category:** Outdated packaging / CI
- **Severity:** Medium
- **Evidence:** No `.github/` directory. `pyproject.toml` `[tool.hatch.build.targets.wheel] packages = ["agent"]` and `[project.scripts] iris = "companion:main"`. `companion.py` and `iris_api.py` live at repo root, not inside `agent/`.
- **Explanation:** An installed wheel cannot run the documented CLI script or the API. CI never existed in this snapshot to catch it.
- **Consequence:** `uv pip install .` / published package would be incomplete.
- **Confidence:** Verified
- **Recommended verification:** `uv build` and inspect wheel contents (mutating; not done).

### B-OD-10 — `docs/adr/` required by agent instructions, absent

- **Category:** Outdated / missing docs
- **Severity:** Low
- **Evidence:** `docs/agents/domain.md` lines 10–16 and 65–68: “Create `docs/adr/`”. `ls docs/adr` → No such file. Root `CLAUDE.md` says `CONTEXT.md` + `docs/adr/` at repo root.
- **Explanation:** Domain skill layout was specified, never instantiated.
- **Consequence:** Architecture decisions (single-user, no Neo4j, journal-as-reflections) have no ADR; agents will relitigate them.
- **Confidence:** Verified
- **Recommended verification:** `find docs -name 'ADR-*'`.

---

## 6. Logical-inconsistency register

### B-LI-01 — New themes are never discovered on the HTTP ingest path

- **Category:** Domain / workflow
- **Severity:** Critical
- **Evidence:** `run_processing_pipeline` (`agent/pipeline.py` 133–148) only `check_persistence()` (match **existing** themes). `discover_themes()` is called from `companion.py` `/discover` (lines 176–181, 829–830) and tests, **not** from `iris_api.py`. `check_persistence` returns `None` if `user_themes` is empty (`persistence.py` 126–128).
- **Explanation:** The SPA can write reflections/habits forever; without a CLI `/discover` (or a test inserting themes), `themes` stays empty, insights stay empty, chat context is “No significant patterns observed recently.”
- **Consequence:** End-to-end “journal → insight → chat” does not work for a new local user. Tests that seed themes hide this.
- **Confidence:** Verified
- **Recommended verification:** Empty DB, POST `/api/journal` five times with mocked embeddings, GET `/api/insights` — expect `[]`.

### B-LI-02 — Pipeline processes “some row in this status”, not the requested `source_id`

- **Category:** Cross-component contract
- **Severity:** Critical
- **Evidence:** `run_processing_pipeline` sets `processing` on `source_id`, then `embeddings.get_items_to_process(source_type, status='processing', limit=1)` (`pipeline.py` 78–81). `Database.get_items_to_process` (`database.py` 764–880) `SELECT … WHERE processing_status = %s LIMIT %s` with **no** `id = source_id` and **no** `user_id`. Content from that row is embedded; `add_embedding` / `check_persistence` still use the **caller’s** `source_id`.
- **Explanation:** Under leftover `processing`/`pending` rows (this host’s `iris_test_db` had historical users), the wrong text is bound to the wrong id. Reproduced: `test_complete_journal_entry_flow` expected the new journal text and got `'Stress 0'`.
- **Consequence:** Cross-user content mix-up in a shared DB; corrupted embeddings; occurrences attached to the wrong source; flaky tests.
- **Confidence:** Verified
- **Recommended verification:** Insert two pending journal rows; call `run_processing_pipeline` for the second id; assert embedding text/source_id.

### B-LI-03 — Dual journal systems (table vs reflection mapping)

- **Category:** Docs vs implementation / frontend vs backend
- **Severity:** High
- **Evidence:** Schema `journal_entries` (`database.py` 154–165). CLI `JournalEntry.create_entry` writes that table. FastAPI `POST /api/journal` (`iris_api.py` 665–680) calls `ReflectionService.create_reflection` and maps `mood` → `energy_level`. `core._get_recent_journal_entries_context` reads `journals.get_recent_entries` (the table). `_get_reflections_context` reads reflections separately. Engine tests almost exclusively `db.create_journal_entry`.
- **Explanation:** The SPA “journal” never populates the store the companion calls “journal”. Chat injection for a UI user shows “No journal entries yet.” while reflections hold the text. CONTEXT.md “Journal Entry” invariants describe the table, not the API mapping.
- **Consequence:** Split brain: CLI analytics and UI analytics are not the same product. Mood is stored as energy.
- **Confidence:** Verified
- **Recommended verification:** POST `/api/journal`, then query both `reflections` and `journal_entries`.

### B-LI-04 — Chat-as-occurrence fix is incomplete: discovery still clusters messages

- **Category:** Domain invariant
- **Severity:** High
- **Evidence:** HEAD `14a4b24` and `pipeline.py` 123–133 correctly skip `check_persistence` for `message`. `Database.get_unassigned_embeddings` (`database.py` 1049–1053) still includes `source_type = 'message'`. `discover_themes()` clusters whatever that query returns. `persistence.py` lines 4–5 and 118 still say journal **and conversations** / `'journal_entry' or 'message'`.
- **Explanation:** CLI `/discover` (or any future job that calls it) reintroduces the exact self-evidence bug HEAD claimed to close.
- **Consequence:** Mentioning a dissipated theme in chat, then discovering themes, resurrects it.
- **Confidence:** Verified (code); runtime discover-after-chat unverified in this session
- **Recommended verification:** Embed a user message matching a dissipated theme, run `discover_themes()`, inspect `theme_occurrences.source_type`.

### B-LI-05 — Body UI contract vs honest stub API

- **Category:** Frontend vs backend
- **Severity:** High
- **Evidence:** `frontend/src/api/body.ts` `GET /api/body/overview` and `/body/day/:date`. Backend only `GET /api/body/source` (`iris_api.py` 1086–1089) returning `{kind:"none", connected:false}`. `useBody` → `getBodyOverview` (`useData.ts` line 8). `BodyScreen.tsx` and `TodayScreen.tsx` render `data.recent`, HRV, readiness. `tests/test_api_body.py` comments “The BodyScreen itself stays on mocks for the demo” and only tests `/api/body/source`.
- **Explanation:** When `VITE_USE_MOCKS` is not true, Body/Today error. When it is true (this machine’s `.env.local`), the UI shows fabricated Fitbit Air data while the API truthfully has none.
- **Consequence:** Users are either blocked or shown fake biometrics — both violate the non-interpretive / no-fabrication stance in the body test docstring.
- **Confidence:** Verified
- **Recommended verification:** `VITE_USE_MOCKS=false` load `/body` against the API.

### B-LI-06 — Connectors and settings actions are theater

- **Category:** Documented vs implemented
- **Severity:** High
- **Evidence:** `iris_api.py` 697–708 catalog including Fitbit/Google/Apple/Spotify/Photos/Messages/Location; comment “no real OAuth/data-source backend yet”. `POST /api/connectors/{id}/{action}` persists `'connected'` in `user_app_settings.connectors`. `SettingsScreen.tsx` cycles connect/pause/disconnect (lines 18–21). Forget/export/delete buttons (lines 34–35, 49) have **no** `onClick`; `forgetFact` API exists but is unwired. Suggestion accept is 204 no-op (`iris_api.py` 926–930).
- **Explanation:** UI language (“PRIMARY”, “on-device sentiment, never content”, “export everything”, “delete & forget”) describes capabilities that are not implemented.
- **Consequence:** False sense of privacy control and data portability. A “connected” Fitbit never syncs (and body API still returns none).
- **Confidence:** Verified
- **Recommended verification:** Connect `fitbit-air`, GET `/api/body/source` (still `none`), click forget/export.

### B-LI-07 — Gate order in CONTEXT.md / contract vs runtime

- **Category:** Docs vs implementation
- **Severity:** Medium
- **Evidence:** `CONTEXT.md` 179–180 and `docs/context_pipeline_contract.md` §2: enablement → confidence → **conflict** → **prioritization** → budget. `core._init_analysis_pipeline` registers enablement, confidence, **budget** only (`core.py` 114–116). Conflict runs after `pipeline.run()` (`core.py` 193–195); then `InsightPrioritizationEngine.rank_insights`; then **another** `max_items` slice (`core.py` 204–209). `budget_gate` comment even says “GATE 4” and “Assumes insights are already ranked” (`pipeline_orchestrator.py` 281–286) but it runs **before** ranking.
- **Explanation:** Budget can drop items before conflict/priority; then budget runs again. Conflict is not a pipeline gate.
- **Consequence:** User `max_items` and engine whitelist do not mean what CONTEXT.md says. Tests that inline-filter (`test_user_control.py` 48–50) do not catch this.
- **Confidence:** Verified
- **Recommended verification:** Feed >5 mixed-confidence insights through `_get_aggregated_context` and log suppression reasons.

### B-LI-08 — Non-interpretive contract vs causal insight kinds and system prompt

- **Category:** Domain contradiction
- **Severity:** Medium
- **Evidence:** `CONTEXT.md` invariant 1: never assign causality. `insights_service.py` `KIND_MAP` sets `leverage` and `decision_impact` to `"causal"` (lines 29–30). `_iris_read` is interpretive (“That shift is what caught my attention.”). `prompts/system_prompt.py` example: “Did something specific happen that triggered that?” — `trigger` is in `FORBIDDEN_PATTERNS` for narratives (`narrative_policy.py` line 27) but **not** applied to the LLM. Leverage docstring in CONTEXT.md says “precede or cause”.
- **Explanation:** Firewall applies only to template narratives, not to chat, review letters, or insight copy. Frontend type `InsightKind` includes `'causal'`.
- **Consequence:** The “epistemic mirror” contract is enforced in one narrow formatter and contradicted everywhere the user actually reads.
- **Confidence:** Verified
- **Recommended verification:** Compare a leverage insight card + a chat turn to `FORBIDDEN_REGEX`.

### B-LI-09 — CLI journal path is a NameError; CLI help is a graveyard

- **Category:** Dead / broken code
- **Severity:** High (CLI), Medium (help text)
- **Evidence:** `agent/journal_entry.py` line 13 imports `db` only; line 61 `journals.create_entry(...)`. mypy: `Name "journals" is not defined`. `companion.py` help lists `/rebuild-vector` (line 72) with **no** handler in the command loop. 24× `logger.error(f"\1: {e}")` (broken replacement). Login/create-user remain after `9d97803`. hdbscan warning filter at top; `hdbscan` is not in `pyproject.toml` dependencies.
- **Explanation:** CLI was not part of the monolith cleanup. `\1` is a failed regex-group substitution left in source.
- **Consequence:** `/journal` crashes; errors log the literal `\1`; documented vector rebuild does nothing.
- **Confidence:** Verified
- **Recommended verification:** `PersonalAICompanion` + `journal_entry_service.create_entry(...)`.

### B-LI-10 — Onboarding API exists; UI is a stub; app does not gate on it

- **Category:** Partial replacement
- **Severity:** Medium
- **Evidence:** `OnboardingScreen.tsx` navigates to `/chat` without calling `api/onboarding.ts`. `App.tsx` default route is `/chat`, no redirect on `onboarding_completed`. Backend `_ONBOARDING_STEPS` and `POST /onboarding/complete` **do not** require all answers (`iris_api.py` 871–875). Tests cover the API in isolation (`tests/test_api_onboarding.py`).
- **Explanation:** First-run flow is unimplemented in the SPA while the backend pretends there is a state machine.
- **Consequence:** `user_app_settings.onboarding_*` stays default; name/threads from onboarding never get set via UI.
- **Confidence:** Verified
- **Recommended verification:** Fresh user, open `/`, confirm no onboarding API calls.

### B-LI-11 — `NARRATIVE_FAIL_MODE` env flag is ignored by the formatter

- **Category:** Duplicated sources of truth
- **Severity:** Medium
- **Evidence:** `agent/config.py` `NARRATIVE_FAIL_MODE` (default `"raise"`). `agent/narrative_policy.py` line 11 **hardcodes** `NARRATIVE_FAIL_MODE = "raise"`. `narrative.py` imports the policy constant, not `settings`. `.env` `NARRATIVE_FAIL_MODE=raise`. `test_fail_closed_silence_mode` monkeypatches `agent.narrative.NARRATIVE_FAIL_MODE`.
- **Explanation:** Production “silence” mode described in `.env.example` cannot be enabled via env.
- **Consequence:** A forbidden lemma in a theme summary raises inside chat context assembly (`format_all`); depending on callers, chat 500s or drops narratives. Cannot fail-closed-to-silence without a code edit.
- **Confidence:** Verified
- **Recommended verification:** Set env to `silence` and format an insight whose summary contains `"cause"`.

### B-LI-12 — Model name split (`gpt-4.1-mini` vs `gpt-4o-mini`)

- **Category:** Config inconsistency
- **Severity:** Medium
- **Evidence:** `PersonalAICompanion.__init__` default `model="gpt-4.1-mini"` (`core.py` 49). `settings.OPENAI_MODEL` default `"gpt-4o-mini"` (`config.py` 25). Review letter constructs `Intelligence(model="gpt-4.1-mini")` (`iris_api.py` 1054). Persistence summaries use `"gpt-4o-mini"` (`persistence.py` 369). Official API docs still list both `gpt-4.1-mini` and `gpt-4o-mini` as of 2026-09-06; ChatGPT retired 4.1 mini on 2026-02-13 but “API, no changes at this time” (openai.com/index/retiring-gpt-4o-and-older-models).
- **Explanation:** Companion ignores `OPENAI_MODEL`. Cost/behavior differ (4.1 mini is priced higher on third-party matrices).
- **Consequence:** Changing `.env` `OPENAI_MODEL` does not change chat.
- **Confidence:** Verified (code); live model availability Unknown without calling OpenAI
- **Recommended verification:** Log `intelligence.model` on a chat request.

### B-LI-13 — Reflections are mutable; CONTEXT.md says sources are immutable

- **Category:** Docs vs implementation
- **Severity:** Medium
- **Evidence:** CONTEXT.md Key Invariant 3. `PUT /api/reflections/{id}` → `update_reflection`. Journal mapping has no update, but the underlying row does. `energy_level and not (1 <= energy_level <= 10)` in `reflections.py` treats `0` as skip-validation (falsy).
- **Explanation:** Soft-delete exists for habits (`is_active=False`) but reflections hard-delete (`DELETE FROM reflections`) without deleting embeddings/occurrences.
- **Consequence:** Orphan embeddings; theme counts that cite deleted text; energy `0` stored.
- **Confidence:** Verified
- **Recommended verification:** Create reflection, embed, DELETE, query `embeddings` and `theme_occurrences`.

### B-LI-14 — Habit skips become theme occurrences; habit color/supports not stored

- **Category:** Domain / contract
- **Severity:** Medium
- **Evidence:** `HabitTracker.log_skip` calls `run_processing_pipeline('habit_completion', skip_id)` (`habits.py` 101–106). Pipeline persistence allow-list includes `habit_completion` (`pipeline.py` 133). Skip rows have `is_skipped=TRUE` (`database.py` 2307–2317). `_habit_to_contract` always `"supports": []`; color from request is returned but **not** written to `habits` (no color column; `iris_api.py` 387–388).
- **Explanation:** A skip is not an occurrence in CONTEXT.md. Frontend `Habit.color` / `supports` are fictional persistence.
- **Consequence:** Skipping yoga can reinforce a “Yoga” theme; colors reset on reload unless the client caches them.
- **Confidence:** Verified
- **Recommended verification:** Skip a habit, inspect `theme_occurrences`; reload `/api/habits/today` and check `color`.

### B-LI-15 — Conversation id and session id are unused for retrieval

- **Category:** API contract
- **Severity:** Medium
- **Evidence:** `_conversation_id_for` returns `conv_{user_id}`. `GET/POST …/{conversation_id}/messages` ignore the path id (`iris_api.py` 262–275, 284–307). Each request constructs `PersonalAICompanion` → new `session_id` timestamp (`core.py` 57) while `ConversationMemory._load_history_from_db` loads last 20 messages **across sessions**.
- **Explanation:** Frontend `types/api.ts` describes real conversations; backend is a single rolling transcript. Tests use `conv_x` and still pass.
- **Consequence:** Cannot isolate sessions; message ids in SSE (`conv_…_timestamp`) do not match DB ids; multi-tab is last-write-wins on one stream of rows.
- **Confidence:** Verified
- **Recommended verification:** Two conversation ids, write to both, GET each — same list.

### B-LI-16 — Double processing on `POST /api/reflections`

- **Category:** Init/runtime
- **Severity:** Medium
- **Evidence:** `ReflectionService.create_reflection` already `run_processing_pipeline('reflection', …)` (`reflections.py` 76–80). API then `background_tasks.add_task(run_processing_pipeline, 'reflection', reflection_id)` (`iris_api.py` 563–565). Journal POST does **not** add a second task (only the service call).
- **Explanation:** First run sets status `complete`; background sets `processing` again and re-embeds. Combined with B-LI-02, the second run can pick a different `processing` row.
- **Consequence:** Double OpenAI spend; unique-occurrence inserts fail; status races.
- **Confidence:** Verified
- **Recommended verification:** Instrument `generate_embedding` around POST `/api/reflections`.

### B-LI-17 — Review/journal mood is energy; sleep metrics are zeros presented as data

- **Category:** Semantic mismatch
- **Severity:** Medium
- **Evidence:** Journal `mood` → `energy_level` (`iris_api.py` 637–638, 648). `_build_review_week` `_avg_energy` → `metrics.moodAvg`; each day `sleepHours: 0` (`iris_api.py` 985). Comment: “Sleep/HRV metrics are 0/omitted — there is no body data source (by design).” Frontend `ReviewWeek.metrics.sleepHoursAvg` is a real field; UI will chart zeros.
- **Explanation:** Contract types say mood 1–10 and sleep hours; backend substitutes another signal or zero.
- **Consequence:** Weekly letter and charts lie by omission/substitution.
- **Confidence:** Verified
- **Recommended verification:** Create journal mood=9, GET `/api/review/latest`, inspect `moodAvg` and `sleepHoursAvg`.

### B-LI-18 — `HabitRepository.create_habit` does not match `Database.create_habit`

- **Category:** Duplicated source of truth
- **Severity:** Low
- **Evidence:** `repositories.py` 79–81 `(categories: list, target_frequency: str)` passed into `db.create_habit` whose signature is `(frequency_type, habit_type, weekly_target, tracking_metric, category)` (`database.py` 2130–2133). Trackers call `db` directly, so HTTP works.
- **Explanation:** The “seam” CONTEXT.md advertises is already drifted.
- **Consequence:** Any caller using the repository (future refactor) mis-binds columns.
- **Confidence:** Verified
- **Recommended verification:** Unit-call `habits.create_habit` via repository.

### B-LI-19 — Intelligence / chat persist provider errors as Iris’s voice

- **Category:** Error handling
- **Severity:** High
- **Evidence:** `Intelligence.chat` returns `f"Error calling API: {str(e)}"` or `"Error: No API client available"` (`intelligence.py` 175–179). `PersonalAICompanion.chat` always `memory.add_message("assistant", response_text)` (`core.py` 158–159). Stream endpoint can also yield `I encountered an error…` (`iris_api.py` 310). Proactive endpoint returns `{"message": "..."}` on failure (line 231) after possibly not persisting.
- **Explanation:** Failures are not typed as errors on the wire (`ApiError`); they become chat history and future LLM context.
- **Consequence:** Later turns condition on “Error calling API”; users think Iris said it.
- **Confidence:** Verified
- **Recommended verification:** Point `OPENAI_API_KEY` at an invalid key in a disposable env and send a chat (do not do this against the user’s live `.env`).

### B-LI-20 — Analytical user preferences are not the settings UI

- **Category:** Two preference stores
- **Severity:** Medium
- **Evidence:** Table `user_preferences` (min_confidence, max_items, enabled_engines) vs `user_app_settings` (tone, density, threads, connectors). Settings API patches only `_PREF_KEY_MAP` (`iris_api.py` 688–695). No HTTP route updates analytical gates. CLI `/settings` still exists in `companion.py`.
- **Explanation:** CONTEXT.md “Changes take effect on the next chat invocation” assumes a settings surface the SPA does not expose.
- **Consequence:** Default medium/5 is frozen for UI users.
- **Confidence:** Verified
- **Recommended verification:** Grep frontend for `min_confidence` / `enabled_engines` (absent).

---

## 7. Risk register

### B-R-01 — Unauthenticated HTTP API; Docker publishes 0.0.0.0

- **Category:** Security
- **Severity:** Critical
- **Evidence:** `9d97803` removed auth. `get_current_user_id` auto-creates `local`/`local` (`iris_api.py` 161–170). Uvicorn local bind `127.0.0.1` (line 1114) but Dockerfile `CMD uvicorn … --host 0.0.0.0 --port 8000` and compose `8000:8000`. Passwords hashed with **SHA256** (`database.py` 24–26, 565–604) for the leftover CLI login.
- **Explanation:** Single-user local-first is an explicit decision, but README still says multi-user and Docker still exposes the port. SHA256 is not a password hash (no salt/work factor).
- **Consequence:** Anyone who can reach :8000 reads/writes the only user’s journal, habits, and chat, and can trigger billed LLM/embedding calls. Stolen `users.password_hash` is brute-force trivial if CLI is reused.
- **Confidence:** Verified
- **Recommended verification:** From another host, `curl` `/api/journal` against a compose-up instance (not done; stack down).

### B-R-02 — Insecure / leftover secrets handling

- **Category:** Security
- **Severity:** Medium
- **Evidence:** `Settings.POSTGRES_PASSWORD` default `"testpassword"` (`config.py` 32). `OPENAI_API_KEY` default `"your_openai_api_key_here"` skips client init only by string compare (`intelligence.py` 41). `.env` is gitignored (good) and contains a real OpenAI key (length 164) plus Neo4j password. `Dockerfile` `COPY .env.example .env` bakes placeholders into the image. `hash_password` SHA256 as above.
- **Explanation:** Fail-open defaults for DB; fail-closed-ish for OpenAI (raises if both clients missing).
- **Consequence:** Accidental deploy with `testpassword` and no auth (B-R-01).
- **Confidence:** Verified
- **Recommended verification:** Start API without `.env` and print `settings.sanitized_dict()` (do not dump secrets).

### B-R-03 — Theme/insight product loop is silently empty

- **Category:** Correctness / silent failure
- **Severity:** Critical
- **Evidence:** Composition of B-LI-01, B-LI-03, B-LI-05, B-LI-06. Pipeline exceptions are logged and swallowed (`reflections.py` 79–80 `print`; `pipeline.py` 154–158 sets `failed` and does not re-raise). InsightsService `_normalize` `except Exception: logger.warning` per engine (`insights_service.py` 70–134).
- **Explanation:** A fresh UI user gets a polished empty app: no themes, no insights, journal text invisible to “journal context”, body either mocked or errored.
- **Consequence:** Silent product failure; users (and tests) can believe the epistemic spine is running.
- **Confidence:** Verified
- **Recommended verification:** New `IRIS_DEFAULT_USER`, SPA-only workflow, query `themes` count.

### B-R-04 — Test suite can charge OpenAI and pollute `iris_test_db`

- **Category:** Test quality / cost / isolation
- **Severity:** High
- **Evidence:** Default collection includes `test_live_system.py`. API tests call `ReflectionService`/`HabitTracker` without mocking `generate_embedding`. `OPENAI_API_KEY` is set in `.env`. After this audit’s pytest run: `iris_test_db` still had **14 users, 45 reflections, 41 embeddings**. `_purge_user` (`conftest.py` 90–137) documents missing FKs and deletes by current `test_user` only — historical users remain. `get_items_to_process` is global (B-LI-02), so leftovers change other tests (failure observed).
- **Explanation:** HEAD claimed 134/134. This run 132/1 with live skipped. Isolation depends on a clean DB that the suite does not guarantee.
- **Consequence:** Flaky CI (if CI existed), unexpected OpenAI bills, cross-test contamination, possible cross-talk if someone pointed tests at `iris_db` before `b4bdcec` (that hole is now guarded by the name-must-contain-`test` check — good).
- **Confidence:** Verified
- **Recommended verification:** `SELECT count(*) FROM users` on `iris_test_db` before/after pytest; run with `OPENAI_API_KEY` unset and see API tests still pass (pipeline errors swallowed).

### B-R-05 — Request path is synchronous LLM + embed; pool max 5

- **Category:** Reliability
- **Severity:** High
- **Evidence:** `memory.add_message` calls `run_processing_pipeline` inline (`memory.py` 69) **before** the LLM call in `chat()`. Stream endpoint waits for full `companion.chat` then splits words (`iris_api.py` 300–317) — not token streaming. Pool `maxconn=5` (`database.py` 55–57). Chat also runs all engines in `analysis_pipeline.run()`. `generate_initial_greeting` embeds+analyzes on every greeting POST.
- **Explanation:** One slow OpenAI call blocks a worker; embedding failure still persists the user message (good) but chat still proceeds; five concurrent chats can exhaust the pool if connections leak (legacy `get_connection()` is a long-lived extra conn).
- **Consequence:** Timeouts, overlapping `processing` rows (feeds B-LI-02), poor UX vs “SSE streaming” comments.
- **Confidence:** Verified
- **Recommended verification:** Two concurrent POSTs to `/messages/stream` with logging around pool checkout.

### B-R-06 — Schema evolution and delete integrity

- **Category:** Data integrity
- **Severity:** High
- **Evidence:** No Alembic. `journal_entries.user_id REFERENCES users(id)` **without** `ON DELETE CASCADE` (`database.py` 158); same for `conversation_messages` (172). `embeddings` has no user column and no FK to sources. `conftest._purge_user` comment lines 93–97 states this explicitly. `DELETE /api/knowledge/{id}` calls `db.delete_theme` (theme CASCADE to occurrences, not to embeddings). IVFFlat indexes created on empty tables with `lists = 100` / `50` (`database.py` 196–203, 220–224) — oversized for a personal corpus (pgvector docs: lists ≈ rows/1000).
- **Explanation:** User delete from CLI/`_purge_user` must manually order deletes or it fails. Orphans accumulate. IVFFlat on tiny tables yields poor recall (silent wrong neighbors), not a crash.
- **Consequence:** Cannot legally `DELETE FROM users` in app DB if journals exist; semantic search quality silently bad; no migration story for column renames.
- **Confidence:** Verified
- **Recommended verification:** `DELETE FROM users WHERE id=…` on a row with journals (expect FK error); `EXPLAIN` a `<=>` query.

### B-R-07 — Privacy narrative vs actual data flow

- **Category:** Privacy
- **Severity:** High
- **Evidence:** Settings copy: “Everything I know about you lives on this device” (`SettingsScreen.tsx` 80). Reality: OpenAI embeddings + chat + review letters send user text off-device whenever keys work. Connectors claim “Messages: On-device sentiment, never content” with no implementation. Untracked `frontend/dist` may bake `VITE_USE_MOCKS=true` including fake `Sam Reeves` / Fitbit series (`frontend/src/lib/mock.ts`). FastAPI will serve that dist.
- **Explanation:** Local-first is storage-local (Postgres on host), not compute-local. Mock-enabled dist is a footgun if served as “production”.
- **Consequence:** User misunderstanding; demo data shown as personal body signals.
- **Confidence:** Verified (code paths); whether current dist was built with mocks Inferred (`Fitbit Air` string present in `frontend/dist/assets/*.js`)
- **Recommended verification:** Search built JS for `VITE_USE_MOCKS` inlined boolean; disable mocks and rebuild when allowed.

### B-R-08 — Naive vs aware datetimes

- **Category:** Correctness
- **Severity:** Medium
- **Evidence:** HEAD commit body: engines “still mix naive and aware and are queued as M3.3”. Schema uses `TIMESTAMPTZ`. Code uses `datetime.now()` without tz in `core.py`, `pipeline.py` backfill, `_age_days` strips tz (`iris_api.py` 721–722), `date.today()` for review (`iris_api.py` 1068). `freeze_time` fixture patches `datetime` on a module list that **omits** `iris_api`, `pipeline`, `insights_service`, `trackers`.
- **Explanation:** Sliding-window engines can mis-bucket “recent” around DST/UTC. Tests that freeze time do not freeze the HTTP layer.
- **Consequence:** Wrong dissipated/reappearing labels near window boundaries; the original 2026-06-14 failure mode adjacent to HEAD’s fix.
- **Confidence:** Verified (mix exists); production mislabel Inferred
- **Recommended verification:** Insert TIMESTAMPTZ occurrences at ±21d and run ResolutionEngine with tz-aware now.

### B-R-09 — Observability and operational recoverability

- **Category:** Operability
- **Severity:** Medium
- **Evidence:** `/health` returns `{status: ok, timestamp}` with **no** DB ping (`iris_api.py` 190–193). Lifespan schema failure is logged, app still yields (`iris_api.py` 56–61). Logs go to `logs/` (gitignored) via `configure_logging`. No backup/restore matching current schema. systemd example is wrong (B-OD-04). Compose volume `iris_data` is declared and unused.
- **Explanation:** A down Postgres still serves a 200 health and an SPA; first real query fails.
- **Consequence:** Orchestrators will not restart a boxed-in API; data recovery is undocumented.
- **Confidence:** Verified
- **Recommended verification:** Stop Postgres, GET `/health`, then GET `/api/user`.

### B-R-10 — Maintainability: monolith leftovers + 1584 ruff / 410 mypy

- **Category:** Maintainability
- **Severity:** Medium
- **Evidence:** ruff 1584, mypy 410, unused `engine_base.py` / `narrative_system.py`, `graph_db` pyc, 2500-line `database.py`, recovery commit deleted 4094 lines but docs/Docker/CLI remain dual-world. `pytest.ini` is a single `norecursedirs = data`.
- **Explanation:** The 2026-09-06 recovery is incomplete. New work will fight ghosts (Poetry, Neo4j, Vanilla, Chroma).
- **Consequence:** High regression risk; agents following README/ARCHITECTURE will undo recovery.
- **Confidence:** Verified
- **Recommended verification:** n/a (counts from this run).

### B-R-11 — Default OpenAI client uses module-level embeddings proxy

- **Category:** Reliability / SDK
- **Severity:** Low
- **Evidence:** `pipeline.py` 27 `openai.api_key = settings.OPENAI_API_KEY` then `openai.embeddings.create`. Installed `openai==2.37.0` exposes `openai._module_client.EmbeddingsProxy` (import check). This is supported today, not the documented `OpenAI()` client used in `intelligence.py`.
- **Explanation:** Two SDK styles; tests mock `agent.pipeline.openai.embeddings.create`.
- **Consequence:** A future SDK major could break ingest while chat still works.
- **Confidence:** Verified
- **Recommended verification:** Official OpenAI Python v3 migration notes when published.

### B-R-12 — Destructive UI affordances without implementation (and the reverse)

- **Category:** Data-loss risk
- **Severity:** Low (UI no-op) / Medium if later wired carelessly
- **Evidence:** Settings “delete & forget” has no handler. API `DELETE /api/knowledge/{fact_id}` **does** delete a theme (`iris_api.py` 789–796) without confirmation beyond HTTP. `uncomplete_habit` DELETEs the completion row (`database.py` 2288–2297), which also drops skip/notes history for that date.
- **Explanation:** Current UI cannot trigger knowledge delete; any client can. Toggle-off is destructive, not a flag.
- **Consequence:** Accidental theme loss; occurrence history for that day gone.
- **Confidence:** Verified
- **Recommended verification:** DELETE `/api/knowledge/{id}` then GET insights.

---

## 8. Unknowns and unresolved questions

1. **Whether `gpt-4.1-mini` still serves this API key** — official model card still lists it (2026-09-06); ChatGPT retirement does not necessarily apply. Not called on purpose.
2. **How much OpenAI spend the 132 passing tests incurred** — embedding mocks are incomplete; key is set. Unverified.
3. **Who the 14 leftover `iris_test_db` users are** — not inspected (privacy). They likely predate this pytest process; they caused B-LI-02’s failing assertion.
4. **Whether `frontend/dist` was built with `VITE_USE_MOCKS=true`** — Inferred from `.env.local` and `Fitbit Air` in the bundle.
5. **Host Postgres 18 vs pgvector 0.8.6 IVFFlat behavior on empty/small tables** — index creation succeeds (schema code); recall quality unverified.
6. **Gemini path** — no Gemini key exercise; SDK is EOL regardless.
7. **Node 26 + Vite 5.4 runtime** — `tsc` passed; `vite build` / `vite dev` not run (would write files / start a server).
8. **Application `iris_db` message contents** — 2 rows exist; not read.
9. **Whether `docker compose up` would work if Dockerfile were fixed** — compose config parses; image build blocked (B-OD-01). Network/volume permissions unverified.
10. **Intended remaining remediation sequence** — HEAD message refers to “M2.6” and “M3.3” but this auditor did not read plan files (independence rule). From code alone, timezone mixing, discovery scheduling, and doc/deploy cleanup are unfinished.
11. **`journal-upgrade` file purpose** — UTF-8 text at repo root, unreferenced.
12. **Browser/mobile support** — no automated UI tests (`frontend/README.md`: “Tests — add Vitest…”).

---

## 9. Prioritized recovery recommendations (do not implement here)

1. **Stop the bleeding on ingest identity (Critical).** Change `get_items_to_process` / `run_processing_pipeline` to `WHERE id = %s` (the `source_id` argument). Add a regression test with two pending rows. This is the bug `test_complete_journal_entry_flow` already tripped.
2. **Make theme formation a first-class HTTP path (Critical).** Either run `discover_themes()` after ingest (async job, not in the request), or fold cluster-on-threshold into `check_persistence`. Until then the SPA cannot produce insights. Exclude `message` (and probably `habit` definitions and skips) from unassigned embeddings.
3. **Pick one journal model (Critical/High).** Either map `/api/journal` onto `journal_entries` (and keep reflections for mood check-ins) or delete/rename the table and teach engines/CLI/core context to use reflections. Stop storing journal `mood` in `energy_level`.
4. **Make Docker/README match the tree (Critical).** Rewrite Dockerfile for uv + `iris_api:app` + `frontend/dist`; or delete compose until that exists. Remove Chroma/FAISS/Vanilla/multi-user claims from README/ARCHITECTURE.
5. **Do not ship 0.0.0.0 without a local-only bind or a real auth story (Critical).** Keep loopback for the single-user app; if Docker is required, publish to `127.0.0.1:8000` only. Replace SHA256 if any password remains.
6. **Quarantine paid APIs in tests (High).** `pytest.mark.live` + default ignore. Mock `generate_embedding` in API fixtures. Truncate or schema-migrate `iris_test_db` per session, not per leftover user. Fix `_purge_user` FKs or use `CREATE DATABASE` from template.
7. **Honest body/connectors/onboarding (High).** Keep `/api/body/source` as none; implement overview as empty/404 with a UI empty-state, or hide the route. Connector “connect” should not persist `connected` without OAuth. Wire onboarding or remove the API. Remove mock-on default for any build that FastAPI serves.
8. **Complete the chat-occurrence invariant (High).** Filter messages out of `get_unassigned_embeddings` / discover; update persistence docstrings; add a test that chat + discover does not resurrect dissipation.
9. **Align gates with CONTEXT.md (Medium).** Register conflict + rank before budget; delete the duplicate slice or the early `budget_gate`. Replace inline “gate” tests with pipeline tests.
10. **Fix CLI or delete it from Quick Start (Medium).** Import `journals` in `journal_entry.py`; remove `/rebuild-vector`; replace `f"\1"` logging; drop login UI if the product is single-user.
11. **Timezone pass (Medium).** One clock (`datetime.now(UTC)`), teach `freeze_time` to patch HTTP/pipeline modules, store naive-free timestamps.
12. **Schema hygiene (Medium).** Versioned migrations; `ON DELETE CASCADE` (or documented purge) for journals/messages/themes/embeddings; user_id on embeddings; don’t create IVFFlat until there is data (or use HNSW).
13. **Replace `google-generativeai` or drop Gemini (Medium).** `google-genai` SDK; or remove the dependency to shrink the EOL surface.
14. **Unify model config (Low/Medium).** `PersonalAICompanion` should read `settings.OPENAI_MODEL`.
15. **Docs/ADR (Low).** Record single-user, pgvector-only, no-Neo4j, journal mapping, and “messages are not occurrences” as ADRs so the next recovery does not relitigate them.

---

## 10. Audit coverage and limitations

Covered from primary evidence:

- Git snapshot, history (26 commits), recovery diff `70bf1d2..HEAD`
- Layout of backend, frontend, tests, docs, Docker, scripts
- Schema as defined in `create_schema()`
- HTTP route list via FastAPI app import
- Domain engines, pipeline, gates, narrative firewall, insights mapping
- Frontend API modules vs backend routes (chat, habits, journal, insights, review, settings, onboarding, body)
- pytest collection + run excluding live (132 pass / 1 fail)
- ruff, mypy, frontend `tsc --noEmit`, compileall
- Compose file parse; host Postgres reachability and DB counts (no content)
- Official Gemini SDK EOL and OpenAI model-card pages (2026-09-06)
- `.env` **keys only** (no secret values copied)

Not done (by rule or risk):

- No file writes in the repo; no commits; no branch checkout
- No `uv sync` / `uv lock` / package installs / `uv python install`
- No `docker compose up`, no docker build, no systemd
- No writes to `iris_db`; no DROP/CREATE DATABASE
- No `npm run build` (would write `frontend/dist`)
- No `tests/test_live_system.py`
- No browser click-through
- No reading of `/home/noodis/.claude/plans/*`, other auditor reports, or session histories
- Did not print secret values

**Independence:** this report does not rely on a prior review text. HEAD’s own commit message mentions an earlier audit’s timezone finding; that was treated as a hint to inspect clocks, then verified in code.

**Working tree:** remained unmodified. `git status --porcelain` at end: empty.

---

### Finding index

| ID | Severity | Category | One-line |
|---|---|---|---|
| B-OD-01 | Critical | Deploy | Dockerfile copies missing `poetry.lock` / `iris_frontend.html` |
| B-OD-02 | High | Docs | README/ARCHITECTURE still Vanilla+Chroma+multi-user |
| B-OD-03 | High | Deps | `google-generativeai` EOL 2025-11-30 |
| B-OD-04 | High | Ops | setup_db.sh / systemd / PGVECTOR guide target old names/paths |
| B-OD-05 | Medium | Toolchain | mypy/black py314 vs venv 3.11.9 |
| B-OD-06 | Medium | Config | Frontend example port 8080; mocks default true |
| B-OD-07 | Medium | Config | Compose PG16/5433 vs host PG18/5432; Chroma/Neo4j leftovers |
| B-OD-08 | Low | API | Pydantic `.dict()` |
| B-OD-09 | Medium | Packaging | No CI; wheel omits `iris_api.py` / `companion.py` |
| B-OD-10 | Low | Docs | `docs/adr/` missing |
| B-LI-01 | Critical | Domain | `discover_themes` never runs on HTTP ingest |
| B-LI-02 | Critical | Pipeline | Process-by-status LIMIT 1, not by source_id (test failed) |
| B-LI-03 | High | Data model | UI journal ≠ `journal_entries` |
| B-LI-04 | High | Domain | Discovery still clusters chat embeddings |
| B-LI-05 | High | Contract | Body overview routes missing; UI/mocks disagree |
| B-LI-06 | High | UX/privacy | Connectors/export/forget are fake or unwired |
| B-LI-07 | Medium | Gates | Budget before rank/conflict; docs disagree |
| B-LI-08 | Medium | Contract | “Causal” insights + prompt vs firewall |
| B-LI-09 | High | CLI | `journals` NameError; `\1` logs; dead `/rebuild-vector` |
| B-LI-10 | Medium | Onboarding | Stub UI, ungated app, complete without answers |
| B-LI-11 | Medium | Config | `NARRATIVE_FAIL_MODE` env ignored |
| B-LI-12 | Medium | Config | `gpt-4.1-mini` vs `OPENAI_MODEL=gpt-4o-mini` |
| B-LI-13 | Medium | Invariant | Reflections mutable/hard-deleted |
| B-LI-14 | Medium | Domain | Skips counted as completions; color not stored |
| B-LI-15 | Medium | API | conversation_id ignored |
| B-LI-16 | Medium | Pipeline | Double pipeline on POST /reflections |
| B-LI-17 | Medium | Semantics | Mood=energy; sleep=0 |
| B-LI-18 | Low | Seams | HabitRepository signature drift |
| B-LI-19 | High | Errors | LLM errors stored as assistant messages |
| B-LI-20 | Medium | Settings | Analytical prefs have no HTTP/UI |
| B-R-01 | Critical | Security | No auth + Docker 0.0.0.0; SHA256 passwords |
| B-R-02 | Medium | Security | Default DB password; example .env in image |
| B-R-03 | Critical | Product | Silent empty insight loop |
| B-R-04 | High | Tests | Live OpenAI in suite; dirty `iris_test_db`; HEAD 134/134 false |
| B-R-05 | High | Reliability | Sync embed+LLM in request; fake SSE; pool 5 |
| B-R-06 | High | Integrity | No migrations; missing CASCADE; IVFFlat lists=100 |
| B-R-07 | High | Privacy | Off-device LLM vs “on this device”; mock body |
| B-R-08 | Medium | Time | Naive/aware mix (acknowledged in HEAD) |
| B-R-09 | Medium | Ops | Health ignores DB; stale systemd |
| B-R-10 | Medium | Maintain | 1584 ruff / 410 mypy / dual worlds |
| B-R-11 | Low | SDK | Module-level OpenAI embeddings proxy |
| B-R-12 | Low | Data loss | Knowledge DELETE real; UI delete fake |

**Counts:** Critical 5 (B-OD-01, B-LI-01, B-LI-02, B-R-01, B-R-03) · High 13 · Medium 19 · Low 5 · Total 42.


# Part 4 — Original review (R0) finding catalog

# R0 Finding Catalog (original review)

Source: `/home/noodis/.claude/plans/graceful-roaming-adleman.md`
Original audit target: `main` @ `ce30b11` plus uncommitted 2026-06-14 working tree
Audit date: 2026-09-06
Note: The same document later records remediation on `recovery/2026-09-06-baseline`. Catalog below tags original claims vs later-claimed fixes.

Current independent-audit snapshot (R1/R2): `recovery/2026-09-06-baseline` @ `14a4b242ae908c36b6a9ecf72ed9f1e5b39bfac3`

Post-R0 commits on current branch:
- `70bf1d2` snapshot uncommitted work
- `c591509` remove Neo4j
- `9e9ac89` lazy PostgreSQL pool
- `9d97803` single-user, no auth, no CORS
- `b4bdcec` dedicated test DB + new-database bootstrap
- `14a4b24` stop counting chat messages as theme occurrences

## Original critical/high findings

| ID | Claim | Later R0 status |
|---|---|---|
| LI-1 / R2 | Two auth models; 24 unauthenticated routes; shared `local` user | Claimed closed by `9d97803` |
| LI-2 | Multi-user vs single-user identity conflict | Claimed closed by owner decision + `9d97803` |
| LI-3 / R9 | Budget gate before conflict/prioritisation | Still open (M2.3 not started) |
| LI-4 / R1 | Pipeline fetches any `processing` row, writes under parameter id | Still open (M2.1 not started) |
| LI-5 / R13 | Double pipeline run on reflections | Still open (M2.2 not started) |
| LI-6 / R14 | Documented async vs synchronous ingest | Still open |
| LI-7 / R7 | Neo4j import-time hard dependency | Claimed closed by `c591509` |
| LI-8 | `/health` always OK; later corrected: process could not start if Postgres down | Partial: lazy pool `9e9ac89`; health probe still open |
| LI-9 / R22 | Frontend/backend contract gaps (body, cursor, habit color) | Still open |
| LI-10 / R10 | Fabricated biometric data in shipped SPA | Still open |
| LI-11 | VITE_USE_MOCKS comment vs only body.ts mocked | Still open |
| LI-12 / R17 | Cache strategy differs; trajectory write-only | Still open |
| LI-13 / R11 | Leverage/decision-impact unread in API chat path | Still open |
| LI-14 / R16 | Naive datetime vs TIMESTAMPTZ | Still open |
| LI-15 / R18 | Mood vs energy conflation | Still open |
| LI-16 / R19 | Two journals (reflections vs journal_entries) | Still open |
| LI-17 / R20 | Two preference systems; UI cannot set analytical gates | Still open |
| LI-18 / R21 | Inert feature flags | Still open |
| LI-19 / R30 | Abandoned refactor modules (~1000 lines) | Partial: graph_sync_queue deleted with Neo4j; engine_base/narrative_system/test_fixtures still listed for M4.3 |
| LI-20 / R31 | Stale CLI duplicate `q` | Claimed closed (`q` removed in `c591509`) |
| LI-21 / R33 | 24 broken CLI log strings `\1` | Still open |
| LI-22 / R35 | Dead identical import guard in core.py | Still open |
| LI-23 / R4 | Tests mutate app database | Claimed closed by `b4bdcec` |
| LI-24 | Tests give false confidence / swallow pipeline failure; later corrected that live embeddings work | Partial: swallowing still open; M2.5 not started |
| LI-25 | CORS wildcard + credentials | Claimed closed by `9d97803` |
| LI-26 | Container serves legacy UI | Claimed retired (Dockerfile/legacy HTML) — M1.3 not fully started |
| LI-27 | API logger never reaches log files | Still open |
| LI-28 / R28 | Duplicate dev deps; undeclared httpx | Still open |
| LI-29 / R36 | Compose Neo4j healthcheck password default mismatch | Claimed closed with Neo4j removal |
| LI-30 | CONTEXT.md schema names mismatch | Still open |
| LI-31 / R25 | Latent SQL identifier interpolation | Still open |
| LI-32 / R15 | Connection pool maxconn=5 vs nested checkouts | Still open |
| R3 | Default SECRET_KEY, SHA-256 passwords, JWT in query | Claimed closed by `9d97803` |
| R5 | Live OPENAI_API_KEY in .env | Still open (rotate) |
| R6 / OD-3 | Docker build fails (poetry.lock) | M1.3 not started; Dockerfile may still be broken |
| R8 | Uncommitted work | Claimed closed by `70bf1d2` snapshot |
| R12 | 4 failing tests | Claimed closed by `14a4b24` (134 passed) |
| R26 | No CI | Still open |
| R27 | No migration framework | Still open |

## Original outdated items

OD-1 Python 3.11 vs 3.14 tooling — open
OD-2 COMPATIBILITY_REPORT / poetry — open
OD-3 Dockerfile poetry.lock — open
OD-4 Docs still list ChromaDB/FAISS — open
OD-5 Docs still list Vanilla JS frontend — open
OD-6 google-generativeai retired — open (R0 later recommends drop)
OD-7 python-jose unmaintained — claimed closed with auth removal
OD-8 Vite 5 / React 18 — optional
OD-9 Four different LLM model defaults — open
OD-10 .env.example vs actual settings — open
OD-11 systemd unit wrong path — open
OD-12 setup_db.sh wrong names — open
OD-13 pydantic `.dict()` — open
OD-14 docs/adr missing — open
OD-15 EXPLORATION_GUIDE DatabaseConnection — open
OD-16 .claude settings poetry — cosmetic
OD-17 origin/dev k8s stranded — retired by owner decision
OD-18 root package-lock.json — open
OD-19 tracked pyc — claimed closed in 70bf1d2
OD-20 frontend .env.example port 8080 vs 8000 — open
OD-21 neo4j driver vs image — claimed moot
OD-22 git remote `gh:` SSH alias missing — later finding; origin now git@github.com (verify)

## Findings added during R0 remediation

LI-33 new-database bootstrap circular: CREATE EXTENSION via register_vector — claimed fixed `b4bdcec`
LI-34 chat messages counted as theme occurrences — claimed fixed `14a4b24`
OD-22 git remote alias — later

## Owner decisions recorded in R0

- Single-user, localhost only
- Drop Neo4j
- UI = frontend/ React SPA
- Deploy: systemd + uvicorn + Postgres on box
- No surviving IRIS Python dataset (iris_db created empty)
- Rails IRIS in learning/ is a scaffold, not the product
- Docker group exclusion is Omarchy policy, not drift


# Part 5 — Original review (R0) full text

Source: `~/.claude/plans/graceful-roaming-adleman.md`

# IRIS — Ground-Zero Audit & Recovery Plan

**Audit date:** 2026-09-06 · **Repo:** `/home/noodis/Iris-01` · **Branch:** `main` @ `ce30b11` (7 commits ahead of `origin/main`, unpushed)
**Last code activity:** 2026-06-14 12:23 (working tree) · **Last commit:** 2026-05-17 · **Dormancy:** ~3 months

> **Mode note:** this session ran in plan mode (read-only). Static inspection, dependency-graph analysis, config/contract diffing and network reachability probes were performed. Test/build/lint/migration execution was **not** performed — see §10 and §3.
>
> **⚠️ One unintended environment change occurred — see §3.1.** Running `uv lock --check` (intended as a read-only lockfile check) caused uv to auto-download CPython 3.11.9 into `~/.local/share/uv/python/`. No repo file changed (`uv.lock`, `pyproject.toml`, `.python-version` all unmodified). Side effect: this **repaired the broken `.venv`**, which is now functional.

---

## Context (why this document exists)

The project has been idle for ~3 months. The request was a full diagnostic — establish what IRIS actually is today, what is stale, where the system contradicts itself, and what the smallest safe path back to a known-good state is. Nothing has been fixed. Everything below is diagnosis plus a proposed, approval-gated roadmap.

Confidence labels used throughout: **[V]** verified by direct evidence · **[I]** strong inference from code/config · **[S]** suspected, needs runtime confirmation · **[U]** unknown.

---

## 1. Executive summary

**What IRIS is.** A local-first personal "epistemic mirror": the user logs habits, reflections and journal entries; a deterministic analytical spine (6 engines: persistence/trajectory/tension/resolution/leverage/decision-impact) detects behavioural patterns; a meta-control layer (confidence → conflict → prioritisation → budget) filters them; a narrative "firewall" renders them in strictly non-causal language; the result is injected into an LLM chat context. PostgreSQL + pgvector is the canonical store, Neo4j a secondary graph lens. ~10.9k lines of backend Python, ~1.4k lines of API, ~4.9k lines of tests, ~2.7k lines of a React/TS SPA, plus ~3.9k lines of design-prototype JSX.

**Current condition: dormant mid-refactor, with substantial uncommitted work.**
- **Builds/installs?** Python deps: **yes** — `uv lock --check` resolves 78 packages, exit 0, and the `.venv` now imports every dependency [V]. Frontend: `node_modules` present, deps installed (vite 5.4.21, TS 5.9.3) [V]; `npm run build` not executed. Docker: **no** — `Dockerfile` does `COPY pyproject.toml poetry.lock ./` but `poetry.lock` was deleted in the uv migration; the build fails at that layer [V].
- **Runs?** **No, not right now.** Nothing listens on 5432/5433 (Postgres), 7688 (Neo4j) or 8000 (API) [V]. `docker.service` is `inactive (dead)` and the user is not in the `docker` group (`groups=noodis,uucp,wheel`), so the documented `docker-compose up` path needs both a daemon start and sudo/group change [V]. Both `agent/database.py:2507 db = Database()` and `agent/graph_db.py:205 graph_db = GraphDB()` construct-and-connect at *import time* and re-raise on failure, so with the databases down the API imports degrade to `COMPANION_AVAILABLE = False` and every data endpoint raises `NameError: db` → HTTP 500 [I].
- **Tests?** Not run here. The last recorded pytest state (`.pytest_cache/v/cache/lastfailed`, written 2026-06-14) lists **4 failing tests**, all in the resolution/stress area [V]. The suite requires a live Postgres *and* (for several API tests) live billable OpenAI calls, and `tests/conftest.py:34` states it runs **against the same database as the app** [V].
- **Deploys?** No. No CI exists on `main` (no `.github/`) [V]; the K8s/deployment assets live only on the un-merged `origin/dev` branch [V]; `scripts/iris.service.example` points at a path that no longer exists [V].

**Most serious findings** (detail in §5/§6):
1. **Wrong-item / cross-user embedding attribution** in the ingestion pipeline — a real data-integrity and user-scoping defect that violates the project's own stated invariant (LI-4, Critical).
2. **Two incompatible auth models in one API** — 24 routes take no credentials at all and resolve a hardcoded `local` user, while the legacy UI still passes tokens to some of them; in the Docker deployment this means logged-in users share one dataset (LI-1, Critical).
3. **Auth crypto is unfit for multi-user use**: default `SECRET_KEY = "your-secret-key-change-in-production"`, unsalted single-round SHA-256 password hashing, JWTs passed in query strings (LI-2/§6 R3, Critical if exposed beyond localhost).
4. **The test suite mutates the application database** and its teardown only cleans 5 of ~12 user-owned tables (R4, Critical for data loss).
5. **Meta-control gate order contradicts both design docs**: the top-K budget cut runs *before* conflict suppression and prioritisation, so the highest-weighted engine's insights are systematically discarded before ranking (LI-3, High).
6. **All meaningful recent work is uncommitted and unpushed** — 7 local commits plus ~5k lines of untracked new code (the entire SPA, the insights service, 10 new test files) exist only on this disk (R8, High).
7. **The shipped SPA renders fabricated biometric data** (HRV, sleep stages, an atrial-fibrillation flag) while `/api/body/source` truthfully reports "No device connected" (LI-10, High for a wellness product).

---

## 2. Current-state map

### 2.1 Components and entry points

| Component | Path | Entry point | Status |
|---|---|---|---|
| HTTP API | `iris_api.py` (1374 ln) | `uvicorn iris_api:app` / `python iris_api.py` (`__main__`, port 8000) | Active, 51 routes + SPA fallback |
| CLI companion | `companion.py` (971 ln) | `iris` script (`pyproject` `[project.scripts]` → `companion:main`) | Active but degraded (24 broken log strings) |
| Orchestrator | `agent/core.py` `PersonalAICompanion` | constructed per request/session | Active |
| Analytical engines | `agent/{persistence,trajectory,tension,resolution,leverage,decision_impact}.py` | via `AnalysisPipeline` / `InsightsService` | Active |
| Meta-control | `agent/{confidence,conflict,prioritization,preferences,preferences_guard}.py` | via `core._get_aggregated_context` | Active, gate order defective |
| Narrative firewall | `agent/narrative.py` + `narrative_policy.py` + `narrative_templates.py` | `NarrativeFormatter.format_all` | Active |
| Ingestion pipeline | `agent/pipeline.py` `run_processing_pipeline` | called from trackers + API background tasks | Active, defective (LI-4) |
| Data layer | `agent/database.py` (2526 ln) + `agent/repositories.py` | `db` singleton, 14 repositories | Active |
| Graph lens | `agent/graph_db.py` | `graph_db` singleton | Import-time hard dependency |
| Insights adapter | `agent/insights_service.py` (untracked) | `/api/insights*` | Active, uncommitted |
| SPA | `frontend/` (React 18 + Vite 5 + TS 5.9, untracked) | `npm run dev` :5173 → proxy /api → :8000; built `frontend/dist` served by FastAPI | Active, uncommitted |
| Legacy UI | `iris_frontend.html` (+ `_enhanced`, `_backup`) | served by `/` when `frontend/dist` absent (i.e. in Docker) | Stale, incompatible auth |
| Design prototype | `frontend/design-prototype/*.jsx` | none (reference only) | Reference |
| Archived UI | `archive/iris-frontend-react/` | none | Staged rename, inert |

**Five user interfaces exist in the tree** (SPA, 3 legacy HTML files, archived React app) plus a JSX design prototype [V].

### 2.2 Data flow (as implemented)

```
UI ──/api/journal, /api/reflections, /api/habits/*──> FastAPI (iris_api.py)
                                                        │
                                        ReflectionService / HabitTracker
                                                        │  (synchronous, in request)
                                              run_processing_pipeline()
                                       ┌────────────────┼────────────────┐
                              OpenAI embeddings   Neo4j projection   PersistenceEngine
                              (text-embedding-       (guarded,        (clusters → themes,
                               3-small, 1536d)      best-effort)       occurrences)
                                                        │
                                          Postgres: embeddings / themes /
                                          theme_occurrences (+ cache invalidation)

Chat: /api/conversations/{id}/messages/stream ──run_in_threadpool──> PersonalAICompanion.chat()
        └─ _get_aggregated_context: AnalysisPipeline(6 engines) → enablement → confidence
           → BUDGET(!) → conflict → prioritisation → budget → NarrativeFormatter → system prompt → LLM
```

### 2.3 Storage

PostgreSQL, ~20 tables created idempotently by `agent/database.py:120 create_schema()` — `CREATE TABLE IF NOT EXISTS` plus ad-hoc `ALTER TABLE … ADD COLUMN IF NOT EXISTS`. **There is no migration framework** (no alembic; `scripts/setup_db.sh` has the alembic invocation commented out) [V]. Vectors are `VECTOR(1536)` with IVFFlat cosine indexes. Neo4j holds a rebuildable graph projection.

### 2.4 External services

OpenAI (chat `gpt-4.1-mini`/`gpt-4o-mini` + embeddings `text-embedding-3-small`), optional Google Gemini (via the retired `google-generativeai` SDK), Neo4j 5, Postgres 16 + pgvector. No OAuth/wearable integrations exist — `CONNECTORS_CATALOG` in `iris_api.py:1008` is a static catalogue with no backend.

### 2.5 Deployment model

Two competing, both-broken stories: (a) `docker-compose.yml` + `Dockerfile` on `main` (poetry-based, build fails); (b) `k8s/` + `Dockerfile.api` + `docker-compose.iris-{core,edge}.yml` + `docs/DEPLOYMENT.md` on `origin/dev` only, last touched 2026-02-05, 18 commits diverged (with duplicated commit pairs suggesting a rebase/cherry-pick tangle) [V].

---

## 3. Validation results

| # | Check | Command | Result | Blocks? |
|---|---|---|---|---|
| 1 | Python syntax, all 87 files under 3.14 | `ast.parse` sweep | **Pass**, 0 syntax errors | no |
| 2 | Internal import resolution | AST import graph vs module list | **1 break**: `q` imports deleted `agent.vector_store` | no |
| 3 | `db.*` / repository call sites resolve | AST attribute check vs class defs | **Pass**, 0 missing methods | no |
| 4 | Lockfile consistency | `uv lock --check` | **Pass** — "Resolved 78 packages", exit 0 | no |
| 5 | Wheel availability per interpreter | `uv.lock` wheel-tag analysis | All native deps ship **cp314** wheels; rest pure-python | no |
| 6 | Virtualenv usable | `.venv/bin/python -c "import …"` | Was **broken** (dangling symlink); **now works** after §3.1; all 16 checked deps import | no (was blocking) |
| 7 | Postgres reachable | `pg_isready -h localhost -p 5433` / `-p 5432` | **Fail** — "no response" (exit 2) on both | **yes** |
| 8 | Neo4j reachable | TCP probe 127.0.0.1:7688 | **Fail** — connection refused | **yes** |
| 9 | API running | TCP probe 127.0.0.1:8000 | **Fail** — connection refused | n/a |
| 10 | Docker usable | `docker ps` | **Fail** — "permission denied … /var/run/docker.sock"; `docker.service` inactive; user not in `docker` group | **yes** |
| 11 | Docker image build | (not run) | **Predicted fail** [I]: `Dockerfile:19 COPY pyproject.toml poetry.lock ./` — `poetry.lock` deleted | **yes** |
| 12 | GitHub issue tracker (per `CLAUDE.md`) | `gh issue list` | **Fail** — `gh` not authenticated | no |
| 13 | Frontend deps installed | `npm ls --depth=0` | **Pass** — 12 top-level deps resolved, no unmet peers | no |
| 14 | Network to registries | `curl pypi.org`, `registry.npmjs.org` | **Pass** (HTTP 200) | no |
| 15 | Last recorded test state | `.pytest_cache/v/cache/lastfailed` | **4 failures** (see below) | — |
| 16 | pytest / npm build / tsc / lint / migrations | not executed (plan mode) | **Unknown** | — |

**Last recorded test failures** (2026-06-14, from `lastfailed`) [V]:
`test_final_system_stress_test.py::test_final_system_integrated_flow`, `test_stress_theme_resolution_debug.py::test_stress_theme_resolution_debug`, `test_resolution_cache_fix.py::test_resolution_override_survives_pipeline`, `test_resolution_override.py::test_stress_theme_exact_scenario` — all in the resolution-cache/override area that the last three commits (`847f402`, `ce47f2f`, `4e80b52`) were actively debugging. **The work stopped mid-debug on exactly this problem.**

**Runtime error history** (`logs/iris_errors.log`, 169 lines, last 2026-06-14): 6 `agent.pipeline` errors, 2 `agent.database` errors; the trailing traceback is a *mocked* `Exception: API Error` from a test run through `generate_embedding` → the retry/backoff path works as designed [V].

### 3.1 Disclosure: unintended environment change

`uv lock --check` was run as a read-only lockfile check. uv resolved `.python-version` (3.11.9), found the interpreter missing, and **auto-downloaded CPython 3.11.9 (20.2 MiB) to `~/.local/share/uv/python/cpython-3.11.9-linux-x86_64-gnu/`**. Verified consequences:

- `uv.lock`, `pyproject.toml`, `.python-version`: **unchanged** (`git status` clean for all three) [V].
- No package was installed into the project; no project file was written.
- Side effect: `.venv/bin/python` (which pointed at exactly that path) resolves again — `Python 3.11.9`, and all project dependencies import [V]. The pre-existing `.venv` from 2026-05-17 was otherwise intact.

To undo: `uv python uninstall 3.11.9` (this would re-break `.venv`). Recommendation: keep it — it restores the last known-good environment for free.

---

## 4. Outdated-items register

| ID | Area | Evidence | Current project state | Current expected state | Impact | Confidence |
|---|---|---|---|---|---|---|
| OD-1 | Python version | `.python-version` = `3.11.9`; `pyproject` `[tool.black] target-version=['py314']`, `[tool.mypy] python_version="3.14"`; 30 tracked `*.cpython-314.pyc`; system `python3` = 3.14.7 | Pin says 3.11, tooling config says 3.14, artefacts from both | One coherent target. Lock analysis shows cp314 wheels exist for `numpy 2.4.5`, `scikit-learn 1.8.0`, `psycopg2-binary 2.9.12`, `pydantic-core 2.46.4`, `cryptography 48`, `grpcio 1.80` — 3.13/3.14 are viable | Formatter/type-checker assume a runtime the venv doesn't use; contributor confusion | V |
| OD-2 | Docs | `COMPATIBILITY_REPORT.md` blames `pypika`, `onnxruntime`, `tokenizers` (ChromaDB deps) and prescribes pyenv+poetry | Reads as current guidance | Obsolete: those deps were removed in `e387b5c` (2026-01-25); poetry replaced by uv in `ce30b11` | Sends a returning developer down a dead path; is the sole rationale for the 3.11 pin | V |
| OD-3 | Container build | `Dockerfile:16-21` installs poetry and `COPY pyproject.toml poetry.lock ./`; `poetry.lock` deleted in working tree | Build fails at COPY | uv-based install (`uv sync --frozen`) | **The documented deployment path is broken** | V |
| OD-4 | Docs vs code | `README.md:33` and `ARCHITECTURE.md:15` list "ChromaDB / FAISS" as the vector lens; `docs/PGVECTOR_MIGRATION.md:3` says migration to pgvector is complete; `agent/vector_store.py` deleted | Two docs contradict a third and the code | pgvector-only | Misleads on architecture; `.env.example` still carries `ANONYMIZED_TELEMETRY # Disable ChromaDB telemetry` | V |
| OD-5 | Docs vs code | `README.md:31`, `ARCHITECTURE.md:20` describe a "Vanilla JS single-file" frontend | The real UI is `frontend/` (React 18/TS/Vite, untracked) | Docs describing the SPA | Onboarding a contributor to the wrong UI | V |
| OD-6 | LLM SDK | `agent/intelligence.py:17` `import google.generativeai`; `uv.lock` pins `google-generativeai 0.8.6` | Retired SDK | PyPI (verified 2026-09-06): 0.8.6 is the last release; "this repository is now considered legacy"; **"All support for this repository ended permanently on November 30, 2025"**; classifier `Development Status :: 7 - Inactive`; successor `google-genai` | Gemini fallback is on an unsupported, unpatched SDK; no security fixes | V |
| OD-7 | Auth library | `pyproject` `python-jose[cryptography]>=3.3.0`, lock 3.5.0 | In use for JWT | Upstream is quiet (last release 3.5.0, 2025-05); Fedora orphaned it as "unmaintained upstream"; FastAPI's own docs moved to **PyJWT** (fastapi#9587) | Security-sensitive dependency without an active maintainer; PyJWT is close to drop-in | V |
| OD-8 | Frontend toolchain | `frontend/package.json` `vite ^5.4.10` (installed 5.4.21), `react ^18.3.1`, `react-router-dom ^6.27` | 3 majors behind | npm registry (verified 2026-09-06): vite `latest` = **8.2.2**, engines `^20.19.0 \|\| >=22.12.0`. Vite 5 engines = `^18 \|\| >=20`, so it **still runs** on the installed Node 26.8.1 | No immediate breakage; unmaintained branch, no security backports | V |
| OD-9 | Model defaults | `config.py:25` `gpt-4o-mini`; `core.py:49` `gpt-4.1-mini`; `persistence.py:369` `gpt-4o-mini`; `iris_api.py:1314` `gpt-4.1-mini`; `llm_provider.py:102` **`gpt-4`** | Four different defaults; `OPENAI_MODEL` honoured on only one path (`intelligence.py:33`) | One configured default | Unpredictable cost/behaviour; `gpt-4` is a legacy model | V |
| OD-10 | Config surface | `.env.example` vs `grep settings.<X>` / `os.getenv` | Documents 7 settings nothing reads: `ENV`, `LOG_LEVEL`, `DEFAULT_MIN_CONFIDENCE`, `DEFAULT_MAX_CONTEXT_ITEMS`, `CONFLICT_SUPPRESSION_ENABLED`, `NARRATIVE_FAIL_MODE`, `ANONYMIZED_TELEMETRY`. Omits 6 that *are* read: `SECRET_KEY`, `OPENAI_MODEL`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `IRIS_DEFAULT_USER`, `IRIS_DEFAULT_PASSWORD` | Example matching reality | Operators believe they can tune behaviour they cannot; **`SECRET_KEY` silently defaults to a public literal** | V |
| OD-11 | Systemd unit | `scripts/iris.service.example:8-12` → `WorkingDirectory=/home/noodis/Myself/apps/personal_ai_agent_minimal`, `ExecStart=.../.venv/bin/python companion.py` | Path doesn't exist; starts the CLI, not the API | Unit for `uvicorn iris_api:app` at the real path | Copy-paste produces a non-starting service | V |
| OD-12 | DB bootstrap | `scripts/setup_db.sh` creates user `iris_app`, DB `iris_agent`, and greps for alembic that isn't there | Mismatch with `POSTGRES_DB=iris_db` / `POSTGRES_USER=iris_user` in `.env`/`config.py` | Consistent names | Following the script produces a DB the app never connects to | V |
| OD-13 | Pydantic API | `iris_api.py:703,871` `updates.dict(exclude_none=True)` | Deprecated v2 API | `model_dump(exclude_none=True)` | Deprecation warnings now, breakage on Pydantic v3 | V |
| OD-14 | Agent docs | `CLAUDE.md` and `docs/agents/domain.md` reference `docs/adr/` | Directory does not exist | Either create ADRs or drop the reference | Agent workflows reference a missing input | V |
| OD-15 | Exploration guide | `EXPLORATION_GUIDE.md:14` names class `DatabaseConnection`; actual class is `Database` (`database.py:29`); quoted file sizes don't match | Stale onboarding doc | Regenerate after refactor | Minor onboarding friction | V |
| OD-16 | Tooling config | `.claude/settings.local.json` allowlists `poetry install`, `pip install`, `.venv/bin/pip` | Old toolchain | uv commands | Cosmetic | V |
| OD-17 | Deployment | `origin/dev` carries `k8s/base/*`, `k8s/overlays/{dev,prod}`, `Dockerfile.api`, `docker-compose.iris-{core,edge}.yml`, `scripts/deploy-iris-*.sh`, `docs/DEPLOYMENT.md`; none on `main` | Deployment assets stranded on a 7-month-old branch that lacks all 2026-05 refactors | One branch of record | Either lost work or a misleading dead branch | V |
| OD-18 | Stray file | root `package-lock.json` = 5-line stub named `personal_ai_agent_minimal` | Vestigial, wrong project name | Delete | Confuses tooling that infers a Node project at root | V |
| OD-19 | VCS hygiene | 30 tracked `agent/__pycache__/*.cpython-314.pyc` despite `.gitignore: __pycache__/` | Bytecode in VCS, showing as modified | Untracked | Permanent spurious diffs; leaks the 3.14 experiment | V |
| OD-20 | Frontend config | `frontend/.env.example:6` `VITE_BACKEND_URL=http://localhost:8080` | Backend listens on **8000** (`iris_api.py:1374`, `vite.config.ts` proxy default) | 8000 | A dev following the example gets a dead proxy | V |
| OD-21 | *Non-finding* | `uv.lock` `neo4j 6.2.0` + compose image `neo4j:5` | — | Neo4j docs (verified 2026-09-06): 6.x driver supports servers 4.4.x, 5.x, 2025.x, 2026.x | **Compatible — no action needed** | V |

---

## 5. Logical-inconsistency register

| ID | Conflicting elements | Evidence / locations | Why inconsistent | Observable or likely consequence | Confidence |
|---|---|---|---|---|---|
| LI-1 | Two auth models in one API | 24 routes use `Depends(get_current_user_id)` (`iris_api.py:276-281`) which resolves/creates a hardcoded user `local` **with no credential check**; 17 routes use `token: str = Query(...)`; 4 take a token in the JSON body; `/api/auth/*` issues JWTs | The same resource family is protected two different ways — e.g. `GET /api/habits` (token) and `POST /api/habits` (no auth) on the identical path | Anyone who can reach the port reads/writes journal, insights, knowledge, settings. Worse: `iris_frontend.html` calls `/api/habits/today?token=…`, but that route ignores the token → **every logged-in user is served the shared `local` user's habits** | V |
| LI-2 | "Multi-user" vs "single-user" | `README.md:3` and `iris_api.py:3` say multi-user; `iris_api.py:266-270` says "this app runs as a personal, single-user local app" | The product identity is undecided in-tree | Auth, tests and docs are each written for a different product | V |
| LI-3 | Gate order vs both design docs | `CONTEXT.md` ("enablement → confidence → conflict → prioritisation → budget"); `docs/context_pipeline_contract.md §2`; implementation `core.py:114-118` registers `budget` as gate order **3**, and `core.py:_get_aggregated_context` runs conflict + prioritisation *after* `pipeline.run()`. `budget_gate` even documents "GATE 4 … **Assumes insights are already ranked by priority**" (`pipeline_orchestrator.py:283`) | Top-K truncation happens before ranking, on engine-registration order (persistence, trajectory, tension, resolution, leverage, decision_impact) | With `max_items=5`, once persistence+trajectory yield 5 insights the **resolution engine (highest `ENGINE_BASE_WEIGHTS` = 1.0), leverage and decision_impact never reach the LLM**. Prioritisation ranks an arbitrary pre-truncated subset | V |
| LI-4 | Pipeline fetches "any row", writes "this row" | `pipeline.py:79-99`: sets `source_id` → `'processing'`, then `embeddings.get_items_to_process(source_type, status='processing', limit=1)`; `database.py:768+` issues `SELECT … WHERE processing_status = %s LIMIT %s` — **no id filter, no ORDER BY**. Content/`user_id`/`occurred_at` come from the fetched row; `add_embedding(source_type, source_id, …)` writes under the *parameter* id | Any second row stuck or concurrently in `'processing'` is silently substituted | Embedding of item A stored against item B; theme occurrences and `user_id` taken from the wrong row → **cross-user theme contamination**, violating CONTEXT.md's "User Scoping" and "Determinism" invariants. A crash leaving one row in `'processing'` poisons every subsequent ingest until manually reset. `tests/test_end_to_end.py:47` already asserts on "the first pending row", i.e. the suite encodes the flaw | V |
| LI-5 | Double pipeline execution | `trackers/reflections.py:76-80` runs `run_processing_pipeline` synchronously inside `create_reflection`; `iris_api.py:818-820` *also* adds it as a `BackgroundTask` | Same work scheduled twice per reflection | 2× OpenAI embedding cost per reflection; second run re-enters the `'processing'` window that makes LI-4 fire | V |
| LI-6 | "Asynchronous analysis" claim vs synchronous ingest | `README.md:20` ("background tasks, sub-500ms"), `ARCHITECTURE.md:47` ("< 100ms"), `docs/context_pipeline_contract.md §1.1`; actual `create_reflection` blocks on OpenAI + clustering, and `async def` endpoints call sync DB code without `run_in_threadpool` (only the chat stream uses it, `iris_api.py:551`) | Documented performance contract is not implemented | POST /journal latency = embedding round-trip; `/api/insights` and `/api/review/latest` run all engines / an LLM call **on the event loop**, blocking every other request | V |
| LI-7 | "Disposable lens" vs import-time dependency | `pipeline.py:126-129` comment: "if it's down, ingestion must still succeed"; but `graph_db.py:205` `graph_db = GraphDB()` at module scope and `_connect()` re-raises on failure (`graph_db.py:44-46`) | Runtime writes are guarded; the import is not | A Neo4j outage makes `import agent.pipeline` (hence the whole API) fail — the opposite of the documented resilience | V |
| LI-8 | Health check vs reality | `iris_api.py:306-310` returns `{"status":"ok"}` unconditionally; the import guard sets `COMPANION_AVAILABLE=False` but `db` is then undefined for 40+ endpoints | Liveness reported without any dependency probe | Orchestrators/monitors see a healthy service that 500s (`NameError`) on every data call | I |
| LI-9 | Frontend ↔ backend contract gaps | `frontend/src/api/body.ts:16,24` call `/body/overview`, `/body/day/{date}` — backend has only `/api/body/source`. `journal.ts:11` sends `?cursor=` and the type declares `nextCursor` — `iris_api.py:914` accepts only `limit` and never returns a cursor. `Habit.color`/`supports` — `_habit_to_contract` recomputes colour from `hid % 4` and always returns `supports: []`; the colour sent on create is echoed once then lost (no `color` column). `Conversation.inferred` and `/inferred` always `[]`. `suggestions/{id}/accept` returns 204 and does nothing | Types promise fields the server never produces | 404s the moment mocks are off; pagination silently broken; habit colours change after reload; UI affordances that do nothing | V |
| LI-10 | Fabricated health data in the shipped build | `frontend/src/lib/mock.ts:287+` `mockBody` generates `readiness`, `hrvMs`, `rhrBpm`, sleep stages and `rhythmFlags: { afib }`; `body.ts` is the only mock-gated module and `.env.local` sets `VITE_USE_MOCKS=true`; the built bundle `frontend/dist/assets/index-C4FfiiD6.js` contains `hrvMs:Math.round(...)` | The SPA served by FastAPI shows synthetic biometrics while `/api/body/source` says "No device connected" | A wellness app presents invented physiological readings (incl. an arrhythmia flag) as the user's own — directly contrary to the project's evidence-only contract | V |
| LI-11 | Comment vs code | `frontend/.env.local:12-14` claims insights/review/body/settings/onboarding "keep rendering on mocks" | Only `body.ts` checks `useMocks()`; the other six call the real API unconditionally | The stated meaning of `VITE_USE_MOCKS` is wrong; flipping it changes only the Body screen | V |
| LI-12 | Cache strategy differs per engine | `resolution.py:59-77` reads `pattern_resolutions` and treats any non-NULL `last_computed_at` as fresh (**no TTL**); `trajectory.py:163` *writes* `theme_trajectories` but `analyze_theme` never reads it | Two engines, two contradictory caching models; one table is write-only | Trajectory recomputes every call (cost); resolution can serve indefinitely old labels if an invalidation path is missed. `add_theme_occurrence` (`database.py:988-993`) invalidates resolutions/tensions/leverage/impacts/confidence but **not** trajectories | V |
| LI-13 | Chat context reads caches nothing populates | `core.py:105-113` registers leverage/decision_impact as `leverage.get_high_leverage_sources(...)` / `decision_impacts.get_significant_impacts(...)` — plain reads of `pattern_leverage` / `decision_impacts` filtered on `last_computed_at IS NOT NULL`. The engines that populate them run only in `companion.py` (CLI) and `insights_service.py` (`/api/insights`) | Two of six engines have no producer in the API request path | In an API-only deployment the chat context contains 4 engines at best — until the user happens to open the Insights screen | V |
| LI-14 | Time zones | 28 naive `datetime.now()` calls in `agent/` vs `TIMESTAMPTZ` columns; timestamps are coerced with `.replace(tzinfo=None)` in 12 places (`resolution.py:102,213`, `confidence.py:88-92`, `tension.py:136,205`, `trajectory.py:365,380`, `prioritization.py:73,128`, `leverage.py:222`, `decision_impact.py:265,279`, `pipeline.py:103`) | UTC wall-clock values are compared against local-time "now" | Every 14/21/30/60/90-day window boundary is shifted by the local UTC offset (+2 h here); "recent vs baseline" classification flips for occurrences near a boundary; DST changes it silently | I |
| LI-15 | Mood ≠ energy | `iris_api.py:1210 _avg_energy` feeds `metrics.moodAvg`/`ReviewDay.mood`/`_mood_word`; `_reflection_to_journal` maps `"mood": r["energy_level"]`; the `reflections.mood` column (inferred from tags by `_infer_mood`) is never surfaced | Two distinct domain concepts collapsed into one wire field | The weekly review's "mood" is really average energy; the stored mood is dead data; CONTEXT.md's Reflection definition is contradicted | V |
| LI-16 | Two journals | New API journal writes to `reflections` (`iris_api.py:925-947`); CLI/`JournalEntry` writes to `journal_entries`; both are separate `source_type`s in the pipeline | The same user concept has two competing stores | Entries created in the UI are invisible to CLI journal commands and vice-versa; "Recent Journal Entries" in the chat context reads only `journal_entries` (`core.py:_get_recent_journal_entries_context`) → the SPA's journal never appears in chat context | V |
| LI-17 | Two preference systems | `user_preferences` (analytical gates: `min_confidence`, `max_items`, `enabled_engines`) vs `user_app_settings` (UI: tone, density, nudges). `PATCH /api/user/preferences` writes only the latter (`_PREF_KEY_MAP`, `iris_api.py:951`) | CONTEXT.md says "User preferences override all gates", but the shipped UI cannot reach them | The documented user control over the meta-control layer is unreachable outside the CLI | V |
| LI-18 | Inert feature flags | `narrative_policy.py:11` hardcodes `NARRATIVE_FAIL_MODE = "raise"`; `constants.py:78` hardcodes `CONFLICT_SUPPRESSION_ENABLED = True`; `config.py` defines both as settings and `.env.example` documents them; `grep settings.NARRATIVE_FAIL_MODE` → 0 hits | Config exists but is never consulted | Setting `NARRATIVE_FAIL_MODE=silence` in production has no effect; a template bug still raises (caught upstream as "Context Retrieval Error", so *all* insights vanish, not just the broken one) | V |
| LI-19 | Abandoned refactor | Zero importers for `agent/engine_base.py` (151 ln), `agent/graph_sync_queue.py` (291 ln), `agent/narrative_system.py` (325 ln), `agent/test_fixtures.py` (230 ln) — all introduced by commits `c06b2e0`/`98d62fd`/`a4b6d4d` (2026-05-17) | ~1000 lines of parallel implementation that nothing calls, alongside the originals they were meant to replace | Readers cannot tell which narrative/engine layer is authoritative; `narrative_system.py` duplicates `narrative*.py` | V |
| LI-20 | Stale CLI duplicate | `q` (969 ln, tracked) is `companion.py` minus the 2026-01 changes; `q:27` still imports the deleted `agent.vector_store` | A second, broken copy of the CLI is committed at the repo root | `python q` crashes on import; a reader can mistake it for a tool | V |
| LI-21 | Broken log messages | `companion.py` lines 127,149,176,194,234,261,313,327,373,395,417,447,477,506,534,559,579,626,662,675,699,732,793,811 — all `logger.error(f"\1: {e}")` | A `sed` backreference was written literally instead of the captured text | 24 CLI error paths log `\1: <exception>` with the operation name lost | V |
| LI-22 | Dead import guard | `core.py:40-43`: `try: from prompts.system_prompt import SYSTEM_PROMPT except (ImportError, ValueError): from prompts.system_prompt import SYSTEM_PROMPT` | Fallback is identical to the guarded import | The except branch can only re-raise; misleading "handled" appearance | V |
| LI-23 | Tests mutate the app database | `tests/conftest.py:34-36` — "we're using the same database as the main app"; `db.create_schema()` session-wide; `test_user` teardown deletes only `theme_occurrences`, `themes`, `journal_entries`, `conversation_messages`, `users` | `habits`, `habit_completions`, `reflections`, `user_app_settings`, `insight_status`, `user_preferences`, `embeddings` rows are left behind (users cascade, so orphans are cleared, but embeddings keyed by `source_id` are not) | Running the suite writes into the personal dataset; leftover rows skew "any pending row" queries (LI-4) and make integration tests order-dependent | V |
| LI-24 | Tests give false confidence | `tests/test_api_journal.py` and the `seeded_week` fixture create reflections with **no mocking** → real `openai.embeddings.create`; `create_reflection` swallows pipeline failure with a bare `print()` (`reflections.py:78-80`) | The API returns 200 and tests pass whether or not the analytical pipeline worked | Green suite while embeddings/themes silently fail; suite costs money and needs network | V |
| LI-25 | CORS | `iris_api.py:78-83`: `allow_origins=["*"]` **with** `allow_credentials=True`; `frontend/src/api/client.ts:38` sends `credentials:'include'` | Wildcard origin + credentials is rejected by browsers per the CORS spec | Credentialed cross-origin calls fail in the browser while the config *looks* permissive; simultaneously any page can call the 24 no-auth endpoints | V |
| LI-26 | Container serves a different app | `Dockerfile:24-28` copies `agent/`, `prompts/`, `iris_api.py`, `iris_frontend.html` — **not** `frontend/dist`; `iris_api.py:295-303` therefore falls back to the legacy HTML | Local dev serves the SPA; the container serves the 2026-01 vanilla UI against the 2026-06 API | Deployed UX ≠ developed UX, and the legacy UI hits the auth mismatch of LI-1 | V |
| LI-27 | Logging blind spot | `logging_config.py` configures only the `agent` logger (`propagate=False`) and sets root to `WARNING`; `iris_api.py:10` uses `logging.getLogger(__name__)` | API-level `logger.info/error` never reaches `logs/iris.log` or `logs/iris_errors.log` | Request-layer failures are invisible in the log files; `LOG_LEVEL` is ignored (hardcoded `DEBUG`) | I |
| LI-28 | Dependency declaration | `pyproject` declares dev deps **twice** (`[project.optional-dependencies].dev` and `[dependency-groups].dev`); `httpx` (required by `fastapi.testclient`) is declared nowhere but present transitively via `openai` | Test tooling depends on an undeclared transitive package | A future `openai` release dropping httpx breaks the whole API test suite | V |
| LI-29 | Compose defaults | `docker-compose.yml`: `NEO4J_AUTH: …/${NEO4J_PASSWORD:?…}` (required) but the healthcheck uses `${NEO4J_PASSWORD:-password}` (defaulted) | Inconsistent handling of the same variable | Healthcheck can authenticate with the wrong password and mark a healthy DB unhealthy | V |
| LI-30 | Doc vs schema names | `CONTEXT.md` Theme: `vector`, `created_at`, invariant `created_at ≤ min(occurred_at)`; schema (`database.py:196`): `centroid_embedding`, plus both `created_at` **and** `first_seen_at`/`last_seen_at` | Glossary doesn't match the columns it describes | Queries/tests written from the glossary reference non-existent fields | V |
| LI-31 | Latent SQL identifier injection | `database.py:1952,1957`: `f"SELECT {key} FROM user_preferences …"` and `INSERT … ({key}) … SET {key} = EXCLUDED.{key}` with no whitelist at the data layer (the only current caller validates 4 keys upstream) | Identifier interpolation instead of `psycopg2.sql.Identifier` | Not reachable from any endpoint today; becomes an injection the moment a preferences endpoint is added | V |
| LI-32 | Connection-pool arithmetic | `database.py:52-59` pool `maxconn=5`; `add_theme_occurrence` holds one connection and calls three `invalidate_*` helpers that each check out **another** connection (`database.py:991-993`); FastAPI's threadpool defaults to 40 workers | Up to 4 connections per ingest, 5 available | Pool exhaustion (`PoolError`) under modest concurrency; nested invalidations also commit outside the outer transaction | I |

---

## 6. Risk register

### Critical — security, data loss, or fundamental failure

| ID | Risk | Basis | Why critical |
|---|---|---|---|
| R1 | Wrong-item / cross-user embedding attribution | LI-4 | Corrupts the canonical store silently; breaks the user-scoping invariant; unrecoverable without recomputation |
| R2 | 24 endpoints accept no credentials; legacy UI + new API share one dataset across logins | LI-1, LI-26 | Full read/write of journal, insights, knowledge and settings for anyone reaching the port |
| R3 | Auth crypto: default `SECRET_KEY` literal (`iris_api.py:51`), unsalted single-round SHA-256 passwords (`database.py:26`), JWTs in query strings (17 routes) | V | Anyone knowing the public default can mint valid tokens; password hashes are trivially rainbow-tabled; tokens land in access logs, proxies and browser history |
| R4 | Test suite runs against the application database and deletes rows | LI-23 | One `pytest` run against a populated personal DB writes and deletes real data |
| R5 | Live-looking `OPENAI_API_KEY` (164 chars, `sk-` prefix) sitting in `.env` since 2026-03-22 | V (gitignored, **not** in git history — `rev-list --objects --all` shows only `.env.example`) | Key age + unknown exposure during a dormant period; rotation is cheap insurance |

### High — blocks an essential workflow or safe deployment

| ID | Risk | Basis |
|---|---|---|
| R6 | Docker build fails (`poetry.lock` gone) — the README's recommended deployment path | OD-3 |
| R7 | Postgres/Neo4j hard dependency at import; `/health` reports OK regardless; failures surface as 500 `NameError` | LI-7, LI-8 |
| R8 | All recent work is uncommitted and unpushed: 7 local commits + ~5k lines untracked (`frontend/`, `agent/insights_service.py`, `agent/logging_config.py`, 10 new test files, `CONTEXT.md`, `EXPLORATION_GUIDE.md`, `docs/agents/`) — plus `origin/dev` holding orphaned K8s work | V |
| R9 | Budget gate before prioritisation silently discards the highest-value insights | LI-3 |
| R10 | Fabricated biometrics (incl. `afib` flag) in the built SPA | LI-10 |
| R11 | Two of six analytical engines never contribute to chat context in the API deployment | LI-13 |
| R12 | The 4 last-known test failures are unresolved and sit in the resolution-cache logic that ships in every chat | V + LI-12 |

### Medium — correctness or maintenance

R13 double embedding cost per reflection (LI-5) · R14 blocking sync work on the event loop, incl. an LLM call in `/api/review/latest` (LI-6) · R15 connection-pool exhaustion (LI-32) · R16 timezone drift in every analytical window (LI-14) · R17 cache-model inconsistency + write-only trajectory table (LI-12) · R18 mood/energy conflation (LI-15) · R19 split journal storage (LI-16) · R20 analytical preferences unreachable from the UI (LI-17) · R21 inert feature flags (LI-18) · R22 missing `/body/*` endpoints and broken journal pagination (LI-9) · R23 retired `google-generativeai` SDK (OD-6) · R24 unmaintained `python-jose` (OD-7) · R25 latent SQL identifier injection (LI-31) · R26 no CI on `main` · R27 no migration framework — schema drift is unversioned and irreversible (§2.3) · R28 `httpx` undeclared (LI-28)

### Low — cleanup / documentation

R29 stale docs (OD-2/4/5/14/15) · R30 ~1000 lines of dead modules (LI-19) · R31 stray root files: `q`, `journal-upgrade`, `23.01.2026.md`, `package-lock.json`, `iris_api.log`, two extra HTML frontends (LI-20) · R32 tracked `.pyc` (OD-19) · R33 24 broken log strings in the CLI (LI-21) · R34 `logs/` is neither tracked nor ignored — `git add .` would commit runtime logs (V; the current logs contain theme/narrative text but no raw journal content — 0 hits for content markers, 24 "Rendered narrative", 56 "Adding message for user") · R35 dead import guard (LI-22) · R36 compose healthcheck default mismatch (LI-29)

---

## 7. Unknowns and questions

| # | Question | Why it matters | Status |
|---|---|---|---|
| Q1 | **Is IRIS single-user-local or multi-user?** | Decides whether R2/R3 are "fix the auth" or "delete the auth". Every other layout choice (CORS, tokens, Docker, K8s) follows from it | U — the repo asserts both |
| Q2 | **Which UI is the product?** `frontend/` SPA, `iris_frontend.html`, or the design prototype | Determines what the Dockerfile ships and which contract gaps (LI-9) must be closed | U — SPA is newest and uncommitted |
| Q3 | **What happened to `origin/dev`?** Is the K8s/CI work wanted, superseded, or abandoned | 13 files of deployment assets and 18 commits either need merging or explicit retirement | U |
| Q4 | **Does the user's real data still exist?** The `postgres_data` / `neo4j_data` docker volumes could not be inspected (no docker access) | Determines whether Phase 0 is "back up a live DB" or "rebuild from scratch" | U — **check before starting anything** |
| Q5 | **Target Python version** — stay on 3.11.9, or move to 3.13/3.14? | Lock analysis says 3.14 is viable; `black`/`mypy` already assume it; `.python-version` says otherwise | U (recommendation: 3.13, see §8) |
| Q6 | **Keep Gemini support?** | Keeping it requires migrating to `google-genai`; dropping it removes 3 packages and a retired SDK | U |
| Q7 | **Is the `OPENAI_API_KEY` in `.env` still live, and should it be rotated?** | It is not in git history, but it has sat on disk through a dormant period | U |
| Q8 | **What is in GitHub Issues?** `CLAUDE.md` names it as the tracker; `gh` is unauthenticated here | There may be recorded intent that changes priorities | U |
| Q9 | **Was the 2026-05 refactor (engine_base / narrative_system / graph_sync_queue) intended to land or be reverted?** | Decides delete-vs-wire for ~1000 lines | U |
| Q10 | **Is a wearable/Fitbit integration actually planned?** | Decides whether `/body/*` gets implemented or the Body screen is removed (LI-10) | U |

---

## 8. Recovery roadmap

Each action lists **dependencies → risk → expected outcome → verification**. Nothing here has been executed.

### Phase 0 — Preserve and reproduce (do this first, before touching anything)

| # | Action | Deps | Risk | Expected outcome | Verification |
|---|---|---|---|---|---|
| 0.1 | Commit or stash the working tree on a `recovery/2026-09-06-baseline` branch: 7 local commits + untracked `frontend/`, `agent/insights_service.py`, `agent/logging_config.py`, 10 test files, `CONTEXT.md`, `EXPLORATION_GUIDE.md`, `docs/agents/`. Exclude `logs/`, `.venv/`, `frontend/node_modules`, `frontend/dist`, `*.pyc` | none | none (additive) | Nothing further can be lost | `git status` clean except deliberate ignores; `git log --stat` shows the snapshot |
| 0.2 | Push that branch to `origin` | 0.1, network | none | Off-machine copy exists | `git rev-list --count origin/recovery/…` matches local |
| 0.3 | Answer Q4: start the docker daemon (`sudo systemctl start docker`) and inspect `docker volume ls` / `docker ps -a` for `postgres_data`, `neo4j_data` **read-only** | sudo | low | Know whether real data exists | Volume list captured in writing |
| 0.4 | If data exists: `pg_dump` to a file outside the repo *before* any schema/test work | 0.3 | low | Restorable snapshot | `pg_restore --list` on the dump |
| 0.5 | Add `logs/`, `frontend/node_modules/`, `frontend/dist/`, `*.tsbuildinfo` to `.gitignore`; `git rm --cached` the 30 tracked `.pyc` | 0.1 | low | Clean diffs; no accidental log commits | `git status` shows no bytecode/logs |

### Phase 1 — Unblock build and startup

| # | Action | Deps | Risk | Expected outcome | Verification |
|---|---|---|---|---|---|
| 1.1 | Decide Q5. **Recommendation: 3.13.15** — already installed via uv, in bugfix support until 2029, and every locked native dep ships cp313 wheels. (3.11.9 also now works; 3.14 works per wheel analysis but is the least-exercised path.) Then make `.python-version`, `[tool.black].target-version` and `[tool.mypy].python_version` agree | 0.1 | low | One coherent runtime | `uv run python -V`; `uv sync --frozen` succeeds |
| 1.2 | Bring the databases up: `docker compose up -d postgres neo4j` (requires daemon + `docker` group or sudo). Confirm `.env` ports (5433/7688) match | 0.3 | medium — first start applies `create_schema()` on connect | Postgres + Neo4j reachable | `pg_isready -h localhost -p 5433` exit 0; bolt 7688 accepts TCP |
| 1.3 | Start the API: `uv run uvicorn iris_api:app --port 8000` | 1.1, 1.2 | low | Service boots without the import-guard fallback | `/health` 200 **and** a real data route (e.g. `/api/habits/today`) returns 200, not 500 |
| 1.4 | Fix the Dockerfile: replace poetry with uv (`COPY pyproject.toml uv.lock`, `uv sync --frozen --no-dev`), stop `COPY .env.example .env`, and copy `frontend/dist` if the SPA is the product (Q2) | 1.1, Q2 | medium | `docker compose build` succeeds and serves the intended UI | `docker compose build agent` exits 0; container `/` serves the chosen UI |
| 1.5 | Run the frontend build once to confirm the toolchain: `npm run lint` then `npm run build` | none | low | Known-good SPA build | `tsc --noEmit` exits 0; `dist/` regenerated |

### Phase 2 — Restore correctness of core workflows

| # | Action | Deps | Risk | Expected outcome | Verification |
|---|---|---|---|---|---|
| 2.1 | **Fix LI-4**: add an id-filtered fetch (`get_item_by_id(source_type, source_id)`) or a `WHERE id = %s` clause, and refuse to proceed if the fetched row's id ≠ `source_id`. Add a stuck-row reset for rows left in `'processing'` | 1.2 | low, high value | Embeddings can only ever be attributed to their own source | New test: two rows in `'processing'`, assert each embedding matches its own text; scan existing data for `embeddings` whose vector ≠ recomputed vector of its source |
| 2.2 | **Fix LI-5**: remove either the synchronous call in `create_reflection` or the `BackgroundTask` in `POST /api/reflections`. Prefer background-only, matching the documented contract (LI-6) | 2.1 | low | One pipeline run per item; POST returns before the embedding round-trip | Count `openai.embeddings.create` calls in a mocked API test = 1 |
| 2.3 | **Fix LI-3**: move `budget_gate` after conflict suppression *and* prioritisation (or delete the in-pipeline budget gate and keep the single slice in `core.py`) | none | low | Top-5 is chosen by rank, not registration order | Test: 6 engines × ≥2 insights, `max_items=3` → the 3 highest-priority survive; assert resolution insights can win |
| 2.4 | **Resolve the 4 known test failures** in the resolution-cache/override area (`test_resolution_cache_fix`, `test_resolution_override`, `test_stress_theme_resolution_debug`, `test_final_system_stress_test`) — this is where work stopped | 1.2, 2.1 | medium — this is the unfinished debugging | Suite green | `pytest tests/ -q` with 0 failures, run against a **dedicated test DB** (2.5) |
| 2.5 | **Fix LI-23**: point tests at a separate database (`IRIS_TEST_POSTGRES_DB` or a per-session schema), and extend `test_user` teardown to every user-owned table | 1.2 | low | Tests can never touch personal data | Run the suite twice; app DB row counts unchanged |
| 2.6 | **Fix LI-24**: mock `agent.pipeline.generate_embedding` in the API tests; make `create_reflection` log (not `print`) and surface pipeline failure | 2.5 | low | Suite is offline, free and honest | Suite passes with no network; a forced embedding failure makes a test fail |
| 2.7 | **Fix LI-7/LI-8**: make `graph_db` lazy (connect on first use) and make `/health` probe Postgres + Neo4j, returning 503 when the canonical store is down | none | low | Neo4j outage degrades the graph lens only | Stop Neo4j → API still starts, journal write succeeds, `/health` reports `neo4j: down` |
| 2.8 | **Decide LI-13**: either run leverage/decision-impact engines in the chat path or drop them from `AnalysisPipeline` and document the API-path engine set | Q9 | low | Documented behaviour matches runtime | Assert on the engines represented in a generated context block |

### Phase 3 — Compatibility and security

| # | Action | Deps | Risk | Expected outcome | Verification |
|---|---|---|---|---|---|
| 3.1 | Settle Q1, then implement one auth model. If single-user: bind to `127.0.0.1`, delete `/api/auth/*` and all `token: str = Query(...)` routes, drop the legacy HTML. If multi-user: put every route behind a real dependency, move tokens to `Authorization: Bearer`, require `SECRET_KEY` (fail fast when unset), replace SHA-256 with bcrypt/argon2 (+ a rehash-on-login path), and tighten CORS to explicit origins | Q1 | high (breaking) | One coherent, non-bypassable auth story | No route resolves a user without a credential (route-table test); no default secret accepted; old hashes migrate on login |
| 3.2 | Rotate the `OPENAI_API_KEY` (Q7) and document `SECRET_KEY` in `.env.example` | Q7 | low | Fresh credentials, documented surface | App runs with the new key; `.env.example` lists every var the code reads |
| 3.3 | Replace `python-jose` with `PyJWT` (near drop-in for HS256) | 3.1 | low | Maintained JWT dependency | Existing token tests pass against PyJWT |
| 3.4 | Decide Q6: migrate `google-generativeai` → `google-genai`, or delete the Gemini path and its deps | Q6 | medium if migrating | No retired SDK in the tree | `uv tree` shows no `google-generativeai`; the chosen provider path has a test |
| 3.5 | Whitelist identifiers in `update_preference` (`psycopg2.sql.Identifier`) | none | low | No identifier interpolation | Unit test: a bogus key raises instead of reaching SQL |
| 3.6 | Introduce a real migration tool (alembic) with an initial revision stamped from `create_schema()`, and stop mutating schema on app startup | 1.2, 0.4 | medium | Versioned, reviewable schema | `alembic upgrade head` on an empty DB reproduces the current schema byte-for-byte (`pg_dump -s` diff) |
| 3.7 | Fix LI-14 (timezone): make the engines UTC-aware end-to-end (`datetime.now(UTC)`, keep tz on DB reads) | 2.4 | medium — changes classification boundaries | Deterministic, offset-free windows | Freeze-time tests around window edges give identical results under `TZ=UTC` and `TZ=Europe/Warsaw` |

### Phase 4 — Align documentation, tests and tooling

4.1 Rewrite `README.md` + `ARCHITECTURE.md` for pgvector-only storage, the React SPA, the real async model and the chosen auth story (OD-4/5, LI-6). 4.2 Retire `COMPATIBILITY_REPORT.md` (or replace it with the current-runtime note) and fix `scripts/iris.service.example` + `scripts/setup_db.sh` names (OD-2/11/12). 4.3 Reconcile `CONTEXT.md` field names with the schema and add ADRs for the decisions taken in Q1/Q2/Q5 (OD-14, LI-30). 4.4 Delete or wire the dead modules and stray root files (LI-19/20/21/22, OD-18/19). 4.5 Add CI: `uv sync --frozen`, `ruff`, `mypy`, `pytest` against a service-container Postgres, plus `npm run lint && npm run build` (R26). 4.6 Close the frontend contract gaps or delete the dead affordances (LI-9), and remove the mock body data from production builds (LI-10). 4.7 Declare `httpx` as a dev dependency and collapse the duplicated dev-dep blocks (LI-28).
*Verification for the phase:* a fresh clone + `README` steps produce a running system on a clean machine, and CI is green on the recovery branch.

### Phase 5 — Optional modernisation

5.1 Vite 5 → 8 and React 18 → 19 (OD-8) — only after 4.5 gives regression cover. 5.2 Async DB layer (`psycopg[async]`/asyncpg) or wrap sync calls in `run_in_threadpool`, and raise the pool ceiling (LI-6, LI-32). 5.3 Unify the caching model across engines and add TTLs (LI-12). 5.4 Merge or formally retire `origin/dev`'s K8s assets (Q3). 5.5 Unify the journal/reflection stores (LI-16) and expose analytical preferences in the UI (LI-17).

---

## 9. Recommended first actions

**Mandatory restoration — the smallest safe sequence to a known, testable state:**

1. **0.1 + 0.2** — branch, commit, push. Everything else risks work that exists in one place only.
2. **0.3 + 0.4** — start docker read-only, confirm whether the `postgres_data` volume holds real data, and dump it if so.
3. **1.1** — pick the Python version and make `.python-version`, black and mypy agree. (The venv already works again — see §3.1 — so this is a consistency fix, not a rebuild.)
4. **1.2 + 1.3** — bring Postgres/Neo4j up and start the API; confirm a data endpoint returns 200. This is the first moment the system is provably alive.
5. **2.5** — repoint the tests at a dedicated database **before** running them. Do not run `pytest` against the personal DB.
6. **2.4** — run the suite and reproduce the 4 known failures; that is the true resumption point of the previous session's work.
7. **2.1 + 2.3** — fix the pipeline attribution bug and the gate order. These are the two defects that quietly corrupt output.

**Explicitly optional (do not conflate with restoration):** Phase 3.3/3.4 dependency swaps, Phase 5 in full, the K8s branch, and any UI rework beyond closing contract gaps.

**Decisions needed from you before Phase 3:** Q1 (single- vs multi-user), Q2 (which UI), Q5 (Python target) — and ideally Q3/Q6/Q9.

---

## 10. Audit coverage and limitations

**Inspected in full:** `README.md`, `ARCHITECTURE.md`, `CONTEXT.md`, `CLAUDE.md`, `COMPATIBILITY_REPORT.md`, `docs/agents/*`, `docs/context_pipeline_contract.md`, `pyproject.toml`, `uv.lock` (programmatically), `pytest.ini`, `.python-version`, `.env`(keys only, values masked), `.env.example`, `.gitignore`, `.dockerignore`, `Dockerfile`, `docker-compose.yml`, `scripts/*`, `agent/config.py`, `agent/constants.py`, `agent/core.py`, `agent/pipeline.py`, `agent/pipeline_orchestrator.py`, `agent/preferences.py`, `agent/narrative.py`, `agent/narrative_policy.py`, `agent/logging_config.py`, `agent/graph_db.py` (structure), `agent/insights_service.py` (structure), `tests/conftest.py`, 4 API test files, `frontend/README.md`, `frontend/package.json`, `frontend/vite.config.ts`, `frontend/src/api/*`, `frontend/src/types/api.ts` (key shapes), `frontend/.env*`.

**Inspected by targeted extraction:** `agent/database.py` (schema DDL, connection layer, ~15 methods of 79), `iris_api.py` (all 51 route signatures + ~700 lines of bodies), `companion.py` (diff vs `q`, error-path grep), the remaining engines (`trajectory`, `resolution`, `tension`, `leverage`, `decision_impact`, `confidence`, `prioritization`, `conflict`) via targeted greps and cache/window logic rather than full reads.

**Analysed programmatically:** AST parse of all 87 Python files (syntax + import graph + dead-module detection + `db.*`/repository call resolution) under Python 3.14.7; `uv.lock` wheel-tag analysis; frontend↔backend route/contract diff; env-var consumption diff.

**Not inspected:** `archive/iris-frontend-react/` (staged rename, inert), `frontend/design-prototype/` (3.9k lines of reference JSX), `iris_frontend_enhanced.html` / `iris_frontend_backup.html` beyond existence, `docs/PGVECTOR_MIGRATION.md` beyond its headings and vector-store claims, `journal-upgrade` (captured plan text) beyond its head, the ~2000 unread lines of `agent/database.py`, and the bodies of ~100 of the 146 test functions.

**Could not be verified (and why):**
- **Nothing was executed**: no `pytest`, no `npm run build`/`tsc`, no `docker build`, no app startup, no migration run — plan mode restricts this session to read-only actions. Every §3 row marked "not run" carries a *predicted* outcome with its evidence, not a result.
- **No database**: Postgres and Neo4j are down, so schema-vs-model drift, actual row counts, orphaned `'processing'` rows, index health and the real cost of LI-4 could not be measured.
- **No docker access**: image build, container behaviour and the contents of the `postgres_data`/`neo4j_data` volumes are unknown (Q4).
- **No GitHub access**: `gh` is unauthenticated, so Issues — the tracker `CLAUDE.md` designates — were not read (Q8). `origin/dev` was analysed from local refs, which have no `FETCH_HEAD`; the remote may have moved since.
- **Runtime-only claims marked [I]**: LI-8 (500 vs 503 behaviour), LI-14 (magnitude of timezone drift), LI-27 (log routing) and LI-32 (pool exhaustion) follow from code reading and need a live system to confirm.
- **External facts** were verified against primary sources on 2026-09-06: PyPI (google-generativeai), python.org devguide (version status), npm registry (vite versions/engines), Neo4j docs (driver compatibility); python-jose's maintenance status rests on secondary sources (Fedora orphan notice, fastapi#9587) plus its release cadence.

**Residual uncertainty:** the four known test failures were not reproduced, so their root cause is inferred from the commit trail (`847f402` → `4e80b52`) and the resolution-cache code, not observed. Until Phase 1 completes, "can it run?" remains a prediction backed by static evidence rather than a demonstrated fact.

---

## 11. Phase 0 execution log (2026-09-06, post-approval)

| Step | Status | Detail |
|---|---|---|
| 0.1 Snapshot on a recovery branch | **Done** | Branch `recovery/2026-09-06-baseline`; commit `70bf1d2` — 171 files, +14,562 / −2,230. Working tree now clean; nothing deleted from disk (`frontend/dist`, `logs/`, `.venv`, `__pycache__` all still present) |
| 0.5 Ignore rules + untrack bytecode | **Done** (folded into `70bf1d2`, ahead of staging as the plan required) | `.gitignore` += `logs/`, `*.log`, `frontend/dist/`, `frontend/node_modules/`, `*.tsbuildinfo`, `.claude/settings.local.json`; `git rm --cached` on 30 tracked `*.pyc`. Verified by dry-run that `logs/iris.log` (514 KB) and the tsbuildinfo files would otherwise have been committed |
| 0.2 Off-machine copy | **Done, with a workaround** | See OD-22 below. Pushed via explicit URL to `git@github.com:noodisD/Iris-01.git`; remote now has `refs/heads/recovery/2026-09-06-baseline` = `70bf1d2`. **All 7 previously-unpushed `main` commits are ancestors of this branch, so they are now on GitHub too** |
| 0.3 Inspect docker volumes (Q4) | **Blocked — needs the user** | Requires `sudo systemctl start docker` and docker-group access |
| 0.4 `pg_dump` if real data exists | **Blocked on 0.3** | — |

### New finding during execution

| ID | Area | Evidence | Current state | Expected | Impact | Confidence |
|---|---|---|---|---|---|---|
| OD-22 | Git remote | `git remote -v` → `gh:noodisD/Iris-01.git`; `~/.ssh/config` (dated 2026-03-04) defines only `Host *`, `Host iris-core`, `Host iris-edge` — **no `Host gh`**; push fails with `ssh: Could not resolve hostname gh` | The remote depends on an SSH alias that no longer exists in the config; every `git fetch`/`push` on this repo has been failing (consistent with the absent `.git/FETCH_HEAD`) | `Host gh` restored in `~/.ssh/config`, or the remote rewritten to `git@github.com:noodisD/Iris-01.git` | Silent loss of remote sync — a plausible reason the 7 commits sat unpushed for ~4 months. SSH auth itself is fine (`ssh -T git@github.com` → "Hi noodisD!") | V |

**Not changed** (deliberately left for your decision): the `origin` URL and `~/.ssh/config` were **not** modified — the push used an explicit URL so no configuration was altered. Pick one:
- `git remote set-url origin git@github.com:noodisD/Iris-01.git` (simplest), or
- restore a `Host gh` block in `~/.ssh/config` (keeps the alias, matches the `iris-core`/`iris-edge` style already there).

### Commands for you to run (Phase 0.3 / 0.4 — these need sudo)

```bash
sudo systemctl start docker                 # daemon is currently inactive
sudo usermod -aG docker $USER               # optional; requires re-login to take effect
docker volume ls | grep -i iris             # Q4: does the real dataset still exist?
docker volume inspect iris-01_postgres_data # size/mountpoint, read-only
```
If the volume holds real data, before anything else:
```bash
docker compose up -d postgres
pg_dump -h localhost -p 5433 -U iris_user -d iris_db -Fc -f ~/iris_db_2026-09-06.dump
```

---

## 12. Revised roadmap — monolith target (supersedes §8)

**Decisions taken 2026-09-06 (owner):**
1. **Single-user, localhost only.** Delete the JWT/token surface rather than fix it.
2. **Drop Neo4j entirely.** Verified: every `graph_db.*` call in the product is a write; the only readers are `graph_sync_queue.py` (zero importers, dead) and a CLI rebuild command. Nothing user-facing ever queries the graph.
3. **UI = `frontend/` (React 18 + TS + Vite), served by the one process.** Established by three independent signals: newest content (2026-06-14 12:20, same hour as the last backend commit), `types/api.ts` is the contract the 24 newest endpoints were written against, and the previous React app was moved to `archive/` by the owner on 2026-06-13.
4. **Deploy: systemd + uvicorn on one box, Postgres alongside.** No orchestrator, no app container.

**Resulting architecture:** one Python process (FastAPI serving `/api/*` and the built SPA from the same origin) + one PostgreSQL with pgvector. Nothing else.

### What the monolith decision retires outright

| Retired | Findings closed |
|---|---|
| Neo4j service, driver, config, `graph_db.py`, `graph_sync_queue.py` | LI-7 (import-time outage coupling), part of LI-19, OD-21 moot |
| JWT/token auth surface, `python-jose`, `SECRET_KEY`, SHA-256 hashing | LI-1, LI-2, R2, R3, OD-7 |
| Wildcard CORS (same-origin once the SPA is served in-process) | LI-25 |
| Three legacy HTML frontends | LI-26, part of LI-9 |
| `origin/dev` K8s overlays, `Dockerfile.api`, iris-core/iris-edge split | Q3, OD-17 |
| App Dockerfile (systemd deploy instead) | OD-3 |

**Still required regardless of architecture:** LI-4 (pipeline attribution), LI-3 (gate order), LI-23/LI-24 (tests vs live DB), R12 (4 failing tests), LI-14 (timezones), LI-5 (double processing), R27 (migrations).

### M1 — Collapse the stack *(no database required; verifiable statically)*

| # | Action | Risk | Verification |
|---|---|---|---|
| M1.1 | **Remove Neo4j**: delete `agent/graph_db.py`, `agent/graph_sync_queue.py`, `tests/test_graph_db.py`; strip the graph block from `pipeline.py`, the `graph_db.close()` calls in `core.py`/`companion.py`, the CLI rebuild command; drop `neo4j` from `pyproject.toml` + relock; drop `NEO4J_*` from `config.py`/`.env.example`; drop the service from `docker-compose.yml` | low — write-only subsystem | AST sweep: zero `graph_db`/`neo4j` references outside history; `uv lock --check` passes; `pytest --collect-only` collects |
| M1.2 | **Single-user auth**: delete `/api/auth/*` and the 4 superseded `/api/chat/*` routes; **convert** (not delete) the 17 `token: str = Query(...)` routes to `Depends(get_current_user_id)` so no capability is lost; remove `create_access_token`/`verify_token`/`get_user_id_from_token`, `python-jose`, `SECRET_KEY`; delete the three legacy HTML files; remove the CORS middleware (same-origin); bind uvicorn to `127.0.0.1` | medium — deletes code paths | Route table has exactly one auth mechanism; no route resolves a user from a query param; SPA's calls all still map to a live route |
| M1.3 | **One deployable**: rewrite `scripts/iris.service.example` (real path, `uvicorn iris_api:app --host 127.0.0.1`, `EnvironmentFile`); reduce `docker-compose.yml` to the `postgres` service only (preserving the existing data volume); delete the app `Dockerfile` and `.dockerignore`; record the retirement of `origin/dev` | low | `systemd-analyze verify` on the unit; compose starts Postgres alone |
| M1.4 | **Runtime consistency**: settle `.python-version` / black / mypy on one version (3.13.15 recommended) | low | `uv sync --frozen` + `uv run python -V` agree |

### M2 — Correctness *(requires the database — blocked on Q4/0.3)*

M2.1 fix LI-4 (id-filtered fetch + mismatch guard + stuck-row reset) · M2.2 remove the duplicate pipeline run (LI-5) · M2.3 move the budget gate after prioritisation (LI-3) · M2.4 isolate the test database and extend teardown (LI-23) · M2.5 mock embeddings in API tests; stop swallowing pipeline failure (LI-24) · M2.6 resolve the 4 known resolution-cache failures (R12) · M2.7 make `/health` probe Postgres and return 503 when down (LI-8) · M2.8 decide leverage/decision-impact in the chat path (LI-13).

### M3 — Compatibility and data safety

M3.1 rotate `OPENAI_API_KEY` · M3.2 alembic, stamped from the current `create_schema()`; stop mutating schema at startup · M3.3 UTC-aware engine windows (LI-14) · M3.4 `.dict()` → `model_dump()` · M3.5 whitelist identifiers in `update_preference` (LI-31) · M3.6 **recommend dropping the Gemini path entirely** (retires `google-generativeai`, OD-6, and one more branch of provider logic — the monolith answer to Q6).

### M4 — Docs, tests, tooling

M4.1 rewrite `README.md`/`ARCHITECTURE.md` for the monolith (one process, one database, pgvector-only, SPA in-process, systemd deploy) · M4.2 retire `COMPATIBILITY_REPORT.md`, fix `scripts/setup_db.sh` naming · M4.3 delete dead modules and stray root files (`q`, `journal-upgrade`, root `package-lock.json`, `engine_base.py`, `narrative_system.py`, `test_fixtures.py`) · M4.4 remove the mock body data from production builds and either implement `/api/body/*` or drop the Body screen (LI-9, LI-10) · M4.5 CI: `uv sync --frozen`, ruff, mypy, pytest against a service Postgres, `npm run build` · M4.6 reconcile `CONTEXT.md` field names with the schema.

### M5 — Optional

Vite 5 → 8, React 18 → 19, async DB layer or threadpool wrapping, unified cache model, journal/reflection store unification, analytical preferences surfaced in the UI.

---

## 13. M1 execution log (2026-09-06)

**Q4 answered by the owner: there is no surviving dataset** — the docker volumes are gone (consistent with the environment reset that also removed the uv-managed Python on 2026-09-02). Consequences: Phase 0.4 (`pg_dump`) is moot and closed; M2.4 (test-database isolation) drops from Critical to Medium — still worth doing, but there is no personal data left to destroy; the analytical spine starts cold, so themes/insights must re-accumulate before the chat context has anything to show.

| Step | Commit | Result |
|---|---|---|
| M1.1 Remove Neo4j | `c591509` | −1,905/+22 across 24 files. `graph_db.py`, `graph_sync_queue.py`, `test_graph_db.py`, the pipeline projection block, graph mocks in 8 tests, `/rebuild-graph`, `NEO4J_*` config, the compose service, the `neo4j` dependency (lock: 78 → 76 packages, also dropping `pytz`; no other version moved). Also removed `q`. Verified: zero references remain, 83 files parse, all internal imports resolve, `uv lock --check` passes, `uv sync` uninstalled the driver |
| M1.2 Single-user collapse | `9d97803` (+ HTML deletions that rode along in `9e9ac89`) | −359/+44 in `iris_api.py`. Deleted `/api/auth/*`, the JWT helpers, the `SECRET_KEY` default, `python-jose` (lock: 76 → 72, also dropping `ecdsa`/`rsa`/`six`), the two duplicate `/api/chat/*` routes, the CORS middleware, the three legacy HTML frontends, `companions_db`. **Converted** (not deleted) the 17 token-in-query routes plus `/api/chat/greeting` and `/api/chat/proactive` to `Depends(get_current_user_id)`, so no capability was lost; the two chat routes also moved onto `run_in_threadpool`. Bound to `127.0.0.1` |
| Lazy connection pool | `9e9ac89` | `Database.__new__` no longer connects — see the correction below |
| M1.3 One deployable | — | Not started (compose reduction, systemd unit, Dockerfile removal) |
| M1.4 Runtime consistency | — | Not started (`.python-version` vs black/mypy) |

**Verification performed** (PostgreSQL still down): `import iris_api` succeeds, FastAPI validates and registers **48 routes** — 45 carrying the single-user dependency, 3 public (`/`, `/health`, the SPA fallback) — **no route takes a `token` query parameter**, no CORS middleware is registered, `COMPANION_AVAILABLE` is `True`, and an AST undefined-name sweep over `iris_api.py` is clean.

### Correction to §5 LI-8 (finding was understated)

The audit said an unreachable database left the API importable with `COMPANION_AVAILABLE=False` and 500s from `NameError`. That was wrong, and the M1.2 verification proved it: `iris_api.py:8` imports `agent.logging_config`, which executes `agent/__init__.py` → `core` → `memory` → `database` → `db = Database()` → connect. The import guard on line 33 never gets a chance to run, so **the process could not start at all** when PostgreSQL was down — strictly worse than reported, and the exact analogue of the Neo4j coupling in LI-7. Fixed in `9e9ac89` by creating the pool on first use (`connection()` and `get_connection()` already had lazy-init checks). `/health` still needs a real dependency probe — that remains M2.7.

### Note on commit boundaries

The three legacy HTML deletions were staged by `git rm` before the scoped `git add agent/database.py`, so they were committed in `9e9ac89` (lazy pool) rather than `9d97803` (single-user), whose message claims them. Content is correct in both; only the narrative is misattributed. Left as-is pending the owner's call, since correcting it means rewriting two already-pushed commits.

### Next: PostgreSQL on the box (native, no container)

Decision 4 was "Postgres on the box", and with no data to migrate there is nothing tying the project to the container. Arch has both packages: `extra/postgresql 18.6-1` and `extra/pgvector 0.8.6-1`. Only `postgresql-libs` (the client) is currently installed; there is no server. Note the version move from the compose image's `pg16` to `pg18` — the schema is vanilla SQL plus pgvector with IVFFlat indexes, with no version-specific features, and `psycopg2-binary 2.9.12` supports 18.

After the server is up, `.env` needs `POSTGRES_PORT=5432` (it currently points at 5433, the compose host mapping), and M1.3 can delete `docker-compose.yml` outright.

---

## 14. Database restored — the project runs (2026-09-06)

**Correction to §11/Q4.** "No data exists" was concluded from `docker volume ls`, which was the wrong test: Omarchy's `omarchy-install-docker-dbs` stores data in the container's own layer, not a named volume. A container named `postgres18` already existed — **image `pgvector/pgvector:pg18`, created 2026-08-18 08:29, exited 2026-09-02** (the same reset that removed the uv-managed Python). The conclusion survives for the Python app: the container holds `iris_rails_development` and `iris_rails_test`, but no `iris_db`. The Python app's data is genuinely gone.

**Also a correction to the audit's docker finding.** "User not in the `docker` group" was filed as an obstacle. It is a deliberate Omarchy security decision, documented in `/usr/share/omarchy/install/config/docker.sh`: the docker group is root-equivalent, so Omarchy leaves users out of it and routes access through `sudo`/polkit, with `omarchy-setup-security-sudoless-docker` as an opt-in. Not drift — policy.

### A Rails IRIS exists (decision needed)

`/home/noodis/learning/iris-rails` — Rails 8.1.3 with `neighbor` (pgvector for ActiveRecord), `ruby-openai`, `solid_cache`/`solid_queue`/`solid_cable` and `kamal`: the full DHH stack. Created 2026-08-18 08:29, last touched 08:32. **Zero git commits, 26 uncommitted generated files, no models, no controllers beyond `ApplicationController`, one migration that only runs `enable_extension "vector"`, stock README.** Its database has `ar_internal_metadata` and `schema_migrations` and nothing else. Read: a ~3-minute scaffold in a `learning/` directory, not a started rewrite. Nothing is lost by leaving it; the owner should confirm the Python monolith is still the target.

### What was done

Rather than recreate the container (the image was already correct), the IRIS database was created inside it:

```sql
CREATE ROLE iris_user LOGIN SUPERUSER;
CREATE DATABASE iris_db OWNER iris_user;
CREATE EXTENSION IF NOT EXISTS vector;   -- run as iris_user, proving the app's own path
```

`.env` was updated: `POSTGRES_PORT` 5433 → 5432 (the container publishes 127.0.0.1:5432). `POSTGRES_PASSWORD` is left as-is and ignored — the container runs `POSTGRES_HOST_AUTH_METHOD=trust` on loopback only. The Rails databases were not touched.

### First verified working state this session

- `db.create_schema()` completed: **21 tables**, `embeddings.vector` and `themes.centroid_embedding` as `vector` columns, both IVFFlat cosine indexes present, pgvector 0.8.6.
- The API boots against the live database and serves real responses: `/health` 200; `/api/habits/today` 200 with the full `HabitsTodayResponse` shape; `/api/journal` 200; `/api/user` 200 — the single-user seam created user `local` (id 1) on first request, exactly as designed.

**Phase 1 verification (§8 items 1.2/1.3) is now satisfied.** M2 is unblocked: the pipeline attribution bug, the gate order, test-database isolation and the four failing resolution tests can all be worked and verified against a live database.

---

## 15. M2 progress — the suite is green (2026-09-06)

| Step | Commit | Result |
|---|---|---|
| M2.4 Test-database isolation | `b4bdcec` | Suite runs against `iris_test_db`, auto-created with pgvector, and refuses to start unless the database name contains "test". `_purge_user` now covers every table a test user can touch, including the pattern caches and embeddings that are not user-keyed |
| — New-database bootstrap | `b4bdcec` | See LI-33 below |
| M2.6 The four June failures | `14a4b24` | **Resolved at root cause.** Full suite: **134 passed, 0 failed** (baseline was 130 passed / 3 failed / 1 error) |
| M2.1 Pipeline attribution (LI-4) | — | Not started |
| M2.2 Duplicate pipeline run (LI-5) | — | Not started |
| M2.3 Gate order (LI-3) | — | Not started |
| M2.5 Mock embeddings in API tests | — | Not started; see the note below |
| M2.7 `/health` dependency probe | — | Not started |

### New findings

| ID | Finding | Evidence | Consequence | Confidence |
|---|---|---|---|---|
| **LI-33** | **The app could never bootstrap a new database.** `_init_pool()` ran `CREATE EXTENSION IF NOT EXISTS vector` through `self.connection()`, which calls pgvector's `register_vector()` first — and that raises `ProgrammingError: vector type not found in the database` when the extension is absent. The statement that installs the extension required the extension | Surfaced the moment the suite was pointed at a genuinely fresh database: 134 errors in 0.47 s | Following the README (create an empty database, start the app) could never work; every working database had been prepared by hand. Fixed in `b4bdcec` | V |
| **LI-34** | **Chat messages were counted as theme occurrences**, contradicting CONTEXT.md (which defines occurrences as journal entries, reflections and habit completions) and `EVIDENCE_WEIGHTS` (which has no `message` entry, so they silently took the 0.5 default meant for a bare habit tick) | `pipeline.py` `should_check_persistence` explicitly opted messages in | **This was the cause of all four June failures.** A chat turn ingested the user's message, matched it to a theme, wrote an occurrence dated now, invalidated the resolution cache, and the recomputed label flipped `dissipated` → `persisting` before the narrative for that same turn was written. Mentioning a dissipated pattern manufactured the evidence that un-dissipated it. Fixed in `14a4b24` | V |

### Correction to §5 LI-24

The audit said the API tests would go green "while embeddings/themes silently fail". A direct probe shows the opposite today: the `OPENAI_API_KEY` in `.env` is valid, `create_reflection` calls `generate_embedding` exactly once, one embedding row is stored and `processing_status` reaches `complete`. The suite does make real, billable OpenAI calls (M2.5 should still mock them), but the analytical path is working, not silently failing. The swallowing in `ReflectionService.create_reflection` remains a latent risk rather than an active failure.

### Note on the three preceding commits

`847f402`, `ce47f2f` and `4e80b52` (2026-05-17) were all aimed at the resolution cache — diagnostic logging, a missing import, and `last_computed_at` on INSERT. The cache was behaving correctly throughout; the defect was upstream in what counted as evidence. The diagnostic logging added in `847f402` is still in `resolution.py` and `narrative.py` and should be trimmed in M4.

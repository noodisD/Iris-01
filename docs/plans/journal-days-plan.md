# Journal redesign, grounded day features, and day comparisons

> **Status (2026-09-25):** approved by the owner and handed over. Nothing below is built yet. Start from a fresh branch off `origin/main` and do Phases 1–3 in order.

## Context

The owner finds the journal screen ("Three lines, please.": three small boxes and an energy picker) cramped. They want one large, Obsidian-style writing pane with basic formatting, and a daily check-in of **energy, mood, sleep quality, stress and focus** (each optional, 1–10).

They also want the phone data to ground patterns in reality. For example, are they more tired on office days than at home? Does screen time or social-app use rise on bad days? Do they feel better and focus better on days they walk more?

Today:
- Location arrives as raw GPS, with no place labels.
- App usage is only package names and seconds.
- Steps are a daily count.
- Nothing turns these into day-level facts, and ADR-0017 requires a new ADR before phone data may feed patterns.

**Owner's decisions:**
- Metrics: mood, sleep quality, stress and focus, plus energy.
- Places: **both** an import of the Google Maps Timeline export (Home/Work labels and trip modes) and the phone's GPS for the days in between, with the owner naming home and office once.
- Editor: **Obsidian-style CodeMirror 6.**

Rules carried over from earlier work:
- The public repo gets invented fixtures only.
- Coordinates never leave the laptop.
- Nothing is sent to a model without a click.
- Comparisons are differences with counts, never causes, and the owner judges them.
- The next migration is **0034** and the next ADR is **0024**.

## Handover: read this first

**Before this plan starts (done by the previous session):** "Chat sees what you approved" is on `main`.
- `agent/approved_context.py` builds a "# What they have approved" block for the chat context: accepted ideas and links, insights and patterns marked "rings true", decisions, accepted phone readings, and confirmed Noticed patterns.
- It runs a list of `(name, fn)` sections, so Phase 3 adds one section without touching the rest.
- `prompts/system_prompt.py` describes that block.

Start from a fresh branch off `origin/main`.

**Working rules, to keep:**
- **The repo is public.**
  - Before every push, run `set -a; . ~/Iris-01/.env; set +a; uv run python ~/.claude/iris/prepush_scan.py origin/main..HEAD` as its own step, and push only when it exits 0.
  - Never put journal text, or the topics the owner writes about, into code, tests, docs or commit messages. Tests use invented neutral fixtures (gardening and cooking are used today).
  - Never print journal content to the terminal. Counts and metadata only.
- **Tests:**
  - pytest runs against a throwaway test database, e.g. `POSTGRES_DB=iris_test_merge uv run pytest -q`. Never the live `iris_db`.
  - Never run two pytest processes at once. Check first with `ps -eo pid=,comm=,args= | awk '$2 ~ /^python/ && /pytest/'`.
  - The gating lint is `uv run ruff check --select F,E9,UP,C4,PIE,PGH,PYI,EXE .`, plus `uv run mypy`.
  - Frontend: `npx vitest run`, `npm run lint`, `npm run build`.
  - Android: `./gradlew :app:testDebugUnitTest :app:assembleDebug`.
- **Migrations** are checksummed and forward-only, one transaction each.
  - Never edit an applied one.
  - After adding a migration, regenerate `tests/schema_snapshot.json` with `python -m tests.test_schema_snapshot --update`, with `POSTGRES_DB` pinned to the test database.
  - Back up the live DB with `pg_dump` into `~/Iris-01/data/backups/` before the server applies a new migration.
- **Nothing is sent to a model** (OpenAI) without the owner clicking, and a new model-backed action shows a cost estimate first. Use `agent.intelligence.Intelligence.estimate`.
- **Deploying:**
  - IRIS runs from `~/Iris-01` on `main`, started with `setsid nohup uv run python scripts/serve_iris.py > data/iris-server.log 2>&1 &`. It serves `127.0.0.1:8000`, the Tailscale door `127.0.0.1:8001` and the phone listener `:8765`.
  - To restart, get the PIDs in one command, then `kill <pid>` in a separate one. Never use `pkill -f` or a grep-kill whose pattern appears in the same command, because it kills its own shell.
  - After a frontend change, `npm run build` in `~/Iris-01/frontend`. The server reads the new files.
  - Install the Android APK with `adb install -r` when the phone is connected over USB.
- **Never** enable Tailscale Funnel. **Never** touch other agents' branches.
- **Flow:** commit on a feature branch, run the privacy scan, push the branch, then fast-forward `main` with `git push origin <branch>:main`.

## Phase 1: journal redesign (web and phone)

**Migration `0034_journal_markdown.sql`**
- Add `reflections.content_format` (`plain` | `markdown`, default `plain`), so imported entries containing `*` or `_` are never stripped.
- The check-in goes into the existing `reflections.metrics` JSONB as `{mood|sleep_quality|stress|focus: {value, scale: 10, source: "checkin"}}`, through the writer in `agent/database.py` (~2976). Energy stays in `energy_level`, so the Decisions and Review screens are unchanged. The tag-inferred `mood` column is left alone.

**Backend**
- New `agent/markdown_text.py` with `plain_text(md)`, built on regexes with no new dependency. It removes headings, quote and list markers, checkboxes, `** __ * _ ~~` and backticks, and turns `[t](u)` into `t` and `[[a|b]]` into `b`.
- Use it for markdown rows in three places:
  1. **Embedding:** `agent/pipeline.py` ~153, together with `strip_prompt_labels`.
  2. **What models read:** the observations entry loader, `agent/ideas/reader.py`, `agent/review_letter.py`, and the episodes reader.
  3. **Quote verification:** `agent/observations.py` `verify_citations`, plus the review letter.

  Quote checks reuse the existing pattern in `agent/episodes.py` (~300–336), where the model reads a readable copy of the entry, and `agent/readable.py` `locate()`, which matches by words and returns the owner's own span. A stored citation is therefore always the original words.
- `iris_api.py` `JournalCreate` gains `text` and `checkin: {energy, mood, sleep_quality, stress, focus}`, and **keeps `lines` and `energy`** so older phone builds still work.
  - `_reflection_to_journal` also returns `text`, `format` and `checkin`.
  - A check-in with no text is allowed, and doesn't queue an embedding.

**Web**
- New dependencies: `@codemirror/state`, `view`, `commands`, `language`, `lang-markdown`, and `@lezer/highlight`.
- New files in `frontend/src/components/journal/`:
  - `MarkdownEditor.tsx`: live styling, with headings sized and bold shown as bold.
  - `markdownCommands.ts`: pure wrap and line-prefix commands.
  - `EditorToolbar.tsx`: bold, italic, H1–H3, bullet, checklist, quote, with shortcuts Mod-B, Mod-I, Mod-Alt-1..3, Mod-Shift-8/9/.
  - `CheckinPicker.tsx`: five rows, generalised from the energy picker.
  - `MarkdownView.tsx`: a safe renderer that builds React elements, with no raw HTML.
- Lazy-loaded like the 3D graph (`IdeasScreen.tsx` `React.lazy`), with a textarea fallback, so the main bundle stays small.
- `JournalScreen.tsx` is rebuilt around one full-height pane, with the check-in beside or above it and entries rendered as Markdown in the list.

**Android**
- `JournalViewModel` posts `{text, format: "markdown", checkin}`.
- The composer becomes a large `OutlinedTextField` with a formatting button row, driven by pure functions in `ui/journal/MarkdownEdits.kt`.
- Five check-in rows reuse the energy chips.
- The list shows headings and bold through an `AnnotatedString`.

**Tests**
- `test_markdown_text.py`.
- Journal API: the old `lines` payload still works, and `text` plus `checkin` round-trips.
- Pipeline: markdown rows are embedded as plain text.
- Citations: a quote written without the `**` marks verifies, and an invented word still fails.
- `markdownCommands.test.ts`.
- `JournalScreen.test.tsx`, with a mocked editor.
- A Kotlin test for `MarkdownEdits`.

## Phase 2: grounded day features

**Migrations**
- `0035_sensor_detail.sql`: add `accuracy_m`, `ended_at` and `detail JSONB` to `sensor_observations`.
- `0036_places_and_days.sql` creates three tables:
  - `places(user_id, name, kind home|office|other, lat, lon, radius_m=150, source owner|timeline)`
  - `app_categories(user_id, package, category)`
  - `day_features(user_id, day, day_kind, home/office/commute minutes, commute_mode, steps, steps_full_day, screen_minutes, screen_by_category JSONB, sleep_minutes, location_coverage)`. This is a cache built only from **confirmed** observations, and it holds no coordinates.

**Backend**
- `agent/sensors/adapters.py` `PixelAdapter` keeps `accuracy_m` and the app category.
- New `agent/sensors/timeline.py`, registered as `google_timeline`:
  - It parses the on-device Timeline export's `semanticSegments`.
  - Visits become `timeline_visit`, with the semantic type (HOME/WORK), the time span and the coordinates.
  - Trips become `timeline_activity`, with the mode, distance and time span.
  - The `"52.1°, 21.0°"` coordinate strings are parsed strictly.
- New route `POST /api/sensors/import/google-timeline`, with an upload size limit, staged through `stage_delivery`.
- A "confirm range" action reuses `commit_batch`, so years of history aren't thousands of clicks.
- New package `agent/days/`:
  - `places.py`: create, edit and remove places, and `suggest_from_timeline()`, the time-weighted centre of confirmed HOME and WORK visits.
  - `features.py`: a pure `compute_day(...)` function.
    - GPS fixes with accuracy worse than 200 m are ignored.
    - Each fix covers the time until the next one, at most 5 minutes.
    - Timeline data wins where it overlaps GPS.
    - Coverage is the known share of 06:00–24:00.
    - **Office day** means at least 180 minutes at the office. **Home day** means at least 80% of known time at home. **Unknown** means coverage below 50%.
    - Commute is travel between home and office.
    - App categories come from the owner's override first, then Android's category, then "other".
    - Sleep counts toward the day you wake up.
  - `recompute(...)` runs after a batch is confirmed or rejected, and for every day when places change.
- Routes: `/api/places`, `/api/app-categories`, and `GET /api/days`, which never returns coordinates.

**Web:** the Sensors screen gains a Places panel (name home and office, accept suggestions from the Timeline), an app-category editor, a Days table, and a Timeline upload with a short "how to export it from Google Maps" note.

**Android**
- `AppUsageReader` adds `ApplicationInfo.category`. This needs a manifest `<queries>` entry for launcher apps, because Android 11+ hides other apps.
- The phone never receives place coordinates.

**Tests**, with coordinates invented near 0,0 and packages `com.example.*`:
- Timeline parsing, including malformed input.
- `compute_day` edge cases: gaps, poor accuracy, crossing midnight, Timeline overlapping GPS.
- Category priority.
- Recompute after a reject.
- `/api/days` never returns coordinates.

## Phase 3: day comparisons, and ADR-0024

**ADR-0024**
- Day comparisons are measured, not written.
- They are labelled as coming from the phone and Timeline.
- They are never quoted, never embedded, and never called a cause.
- Both sides' day counts are always shown, and the thresholds are fixed.

This is the answer ADR-0017 asks for.

**Migration `0037_day_difference_verdicts.sql`:** keyed by `(user_id, outcome, split)`, with the same verdicts as 0032.

**`agent/day_differences.py`**
- Outcomes are the five check-in metrics.
- Splits:
  - office vs home day
  - commute, steps (full days only), screen time, social/video/game share and sleep, each as above vs below your own median, with median days dropped
  - location-based splits only on days with at least 50% coverage
- A comparison is shown only if all three hold:
  - each side has **at least 5 days**;
  - the gap is **at least 1.0 point**;
  - a plain-Python **permutation test** (2000 seeded shuffles) gives **p ≤ 0.01**, which is strict because about 30 comparisons run at once.
- Sentence: "Energy averaged 4.1 on office days (12 days) and 6.3 on home days (9 days)."
- Routes: `GET /api/day-differences` and `PUT /api/day-differences/{outcome}/{split}/verdict`.

**UI:** a "Days compared" section on the Insights screen (web `InsightsScreen.tsx`, Android `ui/patterns/InsightsScreen.kt`), reusing the verdict buttons.

**Chat:** comparisons you mark "rings true" join the approved block, as "measured by the phone, never causes".

**Tests**
- Threshold boundaries: 4 vs 5 days, and a gap of 0.9.
- A deterministic permutation result.
- Median ties.
- A verdict outlives its comparison.
- No wording that implies a cause.
- Only comparisons that ring true reach chat.

## Verification (each phase)

- **Full gate:**
  - pytest on `iris_test_merge` (never concurrently), ruff (gating set), mypy
  - Vitest, lint and build: check that the main chunk doesn't grow by CodeMirror's size
  - `./gradlew testDebugUnitTest assembleDebug`
- Headless-Chromium screenshots of the new journal, Sensors and Insights screens.
- Back up the database before each migration.
- Run `~/.claude/iris/prepush_scan.py origin/main..HEAD` as its own step; push the branch, then fast-forward `main`.
- Restart IRIS, killing by PID from a separate call, never `pkill -f`. Install the APK over USB when the phone is connected.
- **By hand:** write a formatted entry with a check-in on web and phone; confirm the embedding is plain text; import a small Timeline export; name home and office; check the Days table; once enough days exist, judge a comparison and ask chat about it.

## Order and size

Phase 1 is about a day's work. Phase 2 is the largest, because of the Timeline import and the day features. Phase 3 depends on about two weeks of check-ins plus day features before any comparison can appear, so Phases 1 and 2 should ship first, to start collecting days.

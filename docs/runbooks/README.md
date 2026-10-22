# Runbooks for the doctor's checks

`uv run python -m agent.doctor` runs every check, stores the run in `health_checks`,
and prints what changed since the last run, then everything that is not fine. Each
check names its runbook here. `--json` gives the whole report; `--can-restart` says
whether restarting IRIS now would throw away work in progress (exit 0 means yes).

It runs every morning from a systemd timer (`scripts/iris-doctor.{service,timer}.example`),
and IRIS shows the latest run in a banner on every screen but chat: problems first, then
what waits on the owner. Checks that wait on the owner report `waiting`, not `fail`.

## What an agent may do without asking

| Class | Meaning |
|---|---|
| read-only | Look, measure, report. Always allowed. |
| safe-auto | Repairs that change no evidence and cost nothing: prune or vacuum telemetry, re-queue a failed job once, rebuild missing embeddings or passages, clear a stale reading copy. |
| needs-owner | Ask first, with the cost: deleting data, model runs over $0.50, migrations, re-reads that set off a full pattern update, anything that changes evidence. |
| guarded | A restart. Only when `--can-restart` says yes, and after `scripts/backup_db.py` if a migration will apply. |

## Rules for every check
- Print counts, ids and timings. Never print entry, session, questionnaire or chat text.
- Back up with `uv run python scripts/backup_db.py <label>` before any migration or data edit.
- A full pattern update runs for an hour or more on the Flex tier and stores nothing until
  it ends: a restart throws it away. Check `--can-restart` first.
- Tests run only against `IRIS_TEST_POSTGRES_DB=iris_test_claude`, never two at once.

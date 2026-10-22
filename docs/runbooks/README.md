# Runbooks for the doctor's checks

`uv run python -m agent.doctor` runs every check, stores the run in `health_checks`,
and prints what changed since the last run, then everything that is not fine. Each
check names its runbook here. `--json` gives the whole report; `--can-restart` says
whether restarting IRIS now would throw away work in progress (exit 0 means yes).

It runs every morning from a systemd timer (`scripts/iris-doctor.{service,timer}.example`),
and IRIS shows the latest run in a banner on every screen but chat: problems first, then
what waits on the owner. Checks that wait on the owner report `waiting`, not `fail`.

## Repairs the doctor makes itself

`--fix` (used by the daily timer) carries out only safe-auto repairs, each re-queried
rather than trusted from the report, re-checked afterwards, and kept in `health_fixes`.
A repair that writes the database is preceded by a backup unless one less than a day old
exists, and nothing is repaired if that backup fails.

| Check | Repair |
|---|---|
| data.orphan_embeddings | delete vectors whose source is gone |
| data.reading_copies | clear copies whose words drifted; the next read makes new ones |
| data.unembedded | embed the entry (embedding only, so it is not counted in its themes twice) |
| data.passages | cut a long journal entry's missing passages (sessions: re-process by hand) |
| queue.exhausted | re-queue a failed reflection, message, habit, discovery or transcription job, once a week at most; pattern updates and voices passes are left for the owner |
| resources.telemetry | prune spans past retention and vacuum |
| resources.backups | take a backup |


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

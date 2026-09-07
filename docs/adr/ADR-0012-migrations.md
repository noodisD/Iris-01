# ADR-0012: Migrations own the schema

## Status
Accepted — 2026-09-07. Supersedes [ADR-0008](ADR-0008-schema-ownership.md).

## Context
ADR-0008 left `create_schema()` as the schema's owner and deferred migrations.
Its objection to alembic was specific and still stands: with no SQLAlchemy
models alembic cannot autogenerate, so it would mean hand-written raw-SQL
revisions running *alongside* a `create_schema()` that also claimed to own the
schema — two sources of truth for one thing.

The limitation ADR-0008 accepted then came due. `CREATE TABLE IF NOT EXISTS`
plus additive `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` can add a thing and
cannot change one: altering a CHECK constraint, adding `ON DELETE CASCADE` to an
existing foreign key, or changing a column type are silent no-ops against a
database that already exists. Three tracked items were blocked on it by name —
dropping `journal_entries` (ADR-0010), a per-pair key for evidence bundles, and
dropping the unread `theme_trajectories` (ADR-0005).

## Decision
Migrations own the schema, and nothing else touches it. `create_schema()` is
gone rather than kept alongside, so the objection in ADR-0008 does not apply:
there is one owner, and it is one that can express a change.

Each migration is `migrations/NNNN_description.sql`, applied in numeric order,
each in one transaction, recorded in `schema_migrations` with the checksum of
the file that ran. `agent/migrations.py` is the runner; the API's lifespan and
the CLI both call `upgrade()` at startup.

`migrations/0001_initial_schema.sql` was **generated** from `create_schema()` by
extracting every literal passed to `cur.execute()` in source order, not re-typed
from it. Its statements keep their `IF NOT EXISTS` clauses, so applying it to a
database that `create_schema()` already built is a no-op that simply stamps it.

A changed checksum on an already-applied migration is an error, not a warning.
Editing a migration that has run leaves every existing database on the old
definition while new ones get the new one — precisely the silent divergence this
replaces. Fix forward with a new migration.

## Consequences
Constraint changes are now expressible, which unblocks the three items above.
A fresh database and a long-lived one provably agree: a test builds a scratch
database from migrations alone and diffs it against `tests/schema_snapshot.json`.

The snapshot test keeps its job. Migrations say what changed; the snapshot says
what the schema *is*, so a migration that does something other than intended
still shows up as a reviewable diff.

Migrations are forward-only. There is no `downgrade`, because a single-user
local application recovers by restoring a dump, and a rollback path that is
never exercised is a rollback path that does not work.

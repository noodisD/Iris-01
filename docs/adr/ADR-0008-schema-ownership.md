# ADR-0008: `create_schema()` owns the schema; drift is caught by snapshot

## Status
Accepted — 2026-09-06. Revisit when a migration tool is chosen.

## Context
The schema is created idempotently at startup with `CREATE TABLE IF NOT EXISTS`
plus additive `ALTER TABLE … ADD COLUMN IF NOT EXISTS`. That is fine for adding
things and cannot express a change: altering a `CHECK` constraint, adding
`ON DELETE CASCADE` to an existing foreign key, or changing a column type are
silent no-ops against a database that already exists. A developer's fresh
database and a long-lived one can therefore diverge with nothing to say so.

Introducing alembic was considered and rejected for now. The project has no
SQLAlchemy models, so alembic cannot autogenerate; it would mean hand-written
raw-SQL revisions running alongside a `create_schema()` that also claims to own
the schema — two sources of truth for the same thing, which is the failure mode
this project has repeatedly been audited for.

## Decision
`create_schema()` remains the single owner. `tests/test_schema_snapshot.py`
compares the live schema — columns, constraints, indexes — against a committed
snapshot, so any change must be made deliberately and appears in review as a
diff.

## Consequences
Schema drift cannot happen silently, and the snapshot doubles as documentation
of the current shape.

Constraint changes remain impossible to express. Anything needing one — the
`insight_status` orphans after a theme is deleted, a per-pair key for evidence
bundles — is blocked until a migration tool is chosen, and those are recorded in
the plan rather than worked around.

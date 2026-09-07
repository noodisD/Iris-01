"""
Schema drift detection.

The schema is created by agent/database.py: create_schema(), idempotently, with
CREATE TABLE IF NOT EXISTS plus additive ALTERs. That is fine for adding things
and cannot express a change: altering a CHECK constraint, adding ON DELETE
CASCADE to an existing foreign key, or changing a column type are all silently
no-ops against a database that already exists. So a developer's fresh database
and a long-lived one can diverge with nothing to say so.

Until a migration tool owns the schema, this test is the tripwire: it compares
the live schema against a checked-in snapshot, so any change has to be made
deliberately and shows up in review as a diff.

Regenerate after an intentional change:
    python -m tests.test_schema_snapshot --update
"""

import json
from pathlib import Path

from agent.database import db

SNAPSHOT = Path(__file__).parent / "schema_snapshot.json"

#: Created by conftest to mark a database this suite owns. It is test
#: infrastructure, not application schema, so it stays out of the snapshot.
INFRASTRUCTURE_TABLES = {"_iris_test_database"}


def _live_schema() -> dict:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT table_name, column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, column_name;
        """)
        columns = {}
        for table, column, dtype, nullable, default in cur.fetchall():
            if table in INFRASTRUCTURE_TABLES:
                continue
            # Sequence defaults embed the table name and are noise here.
            if default and default.startswith("nextval("):
                default = "nextval(...)"
            columns.setdefault(table, {})[column] = {
                "type": dtype, "nullable": nullable, "default": default,
            }

        cur.execute("""
            SELECT c.conrelid::regclass::text AS table_name, c.conname, c.contype,
                   pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            JOIN pg_namespace n ON n.oid = c.connamespace
            WHERE n.nspname = 'public'
            ORDER BY 1, 2;
        """)
        constraints = {}
        for table, name, ctype, definition in cur.fetchall():
            if table in INFRASTRUCTURE_TABLES:
                continue
            constraints.setdefault(table, {})[name] = {"type": ctype, "definition": definition}

        cur.execute("""
            SELECT tablename, indexname, indexdef FROM pg_indexes
            WHERE schemaname = 'public' ORDER BY 1, 2;
        """)
        indexes = {}
        for table, name, definition in cur.fetchall():
            if table in INFRASTRUCTURE_TABLES:
                continue
            indexes.setdefault(table, {})[name] = definition

    return {"columns": columns, "constraints": constraints, "indexes": indexes}


def test_schema_matches_the_committed_snapshot(setup_test_database):
    assert SNAPSHOT.exists(), (
        "no schema snapshot committed; generate one with "
        "`python -m tests.test_schema_snapshot --update`"
    )
    expected = json.loads(SNAPSHOT.read_text())
    actual = _live_schema()

    differences = []
    for section in ("columns", "constraints", "indexes"):
        for table in sorted(set(expected[section]) | set(actual[section])):
            want = expected[section].get(table, {})
            have = actual[section].get(table, {})
            for key in sorted(set(want) | set(have)):
                if want.get(key) != have.get(key):
                    differences.append(
                        f"  {section}.{table}.{key}: snapshot={want.get(key)!r} live={have.get(key)!r}"
                    )

    assert not differences, (
        "the live schema no longer matches tests/schema_snapshot.json:\n"
        + "\n".join(differences)
        + "\n\nIf the change was intended, regenerate with "
          "`python -m tests.test_schema_snapshot --update` and review the diff."
    )


if __name__ == "__main__":
    import sys

    if "--update" in sys.argv:
        db.create_schema()
        SNAPSHOT.write_text(json.dumps(_live_schema(), indent=2, sort_keys=True) + "\n")
        print(f"wrote {SNAPSHOT}")

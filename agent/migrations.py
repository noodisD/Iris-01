"""
Schema migrations.

The schema used to be built by `create_schema()`: idempotent
`CREATE TABLE IF NOT EXISTS` plus additive `ALTER TABLE ... ADD COLUMN IF NOT
EXISTS`. That is fine for adding things and cannot express a *change*. Altering
a CHECK constraint, adding ON DELETE CASCADE to an existing foreign key, or
changing a column type are silent no-ops against a database that already exists,
so a developer's fresh database and a long-lived one could diverge with nothing
to say so.

Alembic was considered and rejected (ADR-0008): with no SQLAlchemy models it
cannot autogenerate, so it would mean hand-written raw-SQL revisions running
alongside a create_schema() that also claimed to own the schema — two sources of
truth for one thing, which is the failure mode this project keeps being audited
for. This is the same hand-written SQL without the second owner: migrations are
the only thing that touches the schema.

Each migration is a file in `migrations/` named `NNNN_description.sql`. They are
applied in numeric order, each in one transaction, and recorded in
`schema_migrations` with a checksum of the file that was applied.

The checksum is not ceremony. Editing a migration that has already run leaves
every existing database on the old definition while new ones get the new one —
exactly the silent divergence this replaces — so a changed checksum is an error,
not a warning. Fix it forward with a new migration.
"""

import hashlib
import logging
import re
from pathlib import Path

from .database import db

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

_FILENAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


class MigrationError(RuntimeError):
    """Raised when the migration history and the files disagree."""


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def discover() -> list[tuple[str, Path]]:
    """Every migration on disk, in the order they must be applied."""
    if not MIGRATIONS_DIR.is_dir():
        return []

    found = []
    for path in sorted(MIGRATIONS_DIR.iterdir()):
        if path.suffix != ".sql":
            continue
        m = _FILENAME.match(path.name)
        if not m:
            raise MigrationError(
                f"{path.name} is not a valid migration name. Use "
                "NNNN_lower_snake_case.sql, e.g. 0002_add_pair_evidence_key.sql"
            )
        found.append((m.group(1), path))

    versions = [v for v, _ in found]
    duplicates = {v for v in versions if versions.count(v) > 1}
    if duplicates:
        raise MigrationError(f"duplicate migration numbers: {sorted(duplicates)}")
    return found


def _ensure_ledger(cur) -> None:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(4) PRIMARY KEY,
            name TEXT NOT NULL,
            checksum VARCHAR(64) NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)


def applied() -> dict[str, dict]:
    """Migrations this database has already run, by version."""
    with db.connection() as conn, conn.cursor() as cur:
        _ensure_ledger(cur)
        conn.commit()
        cur.execute("SELECT version, name, checksum, applied_at FROM schema_migrations;")
        return {
            r[0]: {"name": r[1], "checksum": r[2], "applied_at": r[3]}
            for r in cur.fetchall()
        }


def pending() -> list[tuple[str, Path]]:
    """Migrations on disk that this database has not run."""
    done = applied()
    return [(v, p) for v, p in discover() if v not in done]


def current_version() -> str | None:
    done = applied()
    return max(done) if done else None


def upgrade() -> list[str]:
    """Apply every pending migration. Returns the versions applied."""
    on_disk = discover()
    done = applied()

    # A migration that has already run must not have changed underneath us.
    for version, path in on_disk:
        if version in done:
            live = _checksum(path.read_text())
            if live != done[version]["checksum"]:
                raise MigrationError(
                    f"migration {path.name} has changed since it was applied "
                    f"(recorded {done[version]['checksum'][:12]}, file "
                    f"{live[:12]}). Databases that already ran it still have the "
                    "old definition. Add a new migration instead of editing this "
                    "one."
                )

    # A version recorded but absent from disk means someone is running an older
    # checkout against a newer database; saying so beats a confusing failure.
    missing = sorted(set(done) - {v for v, _ in on_disk})
    if missing:
        raise MigrationError(
            f"database has migrations {missing} that are not in this checkout. "
            "The code is older than the database it is pointed at."
        )

    ran = []
    for version, path in on_disk:
        if version in done:
            continue
        sql = path.read_text()
        logger.info(f"Applying migration {path.name}")
        with db.connection() as conn, conn.cursor() as cur:
            _ensure_ledger(cur)
            try:
                cur.execute(sql)
                cur.execute(
                    """INSERT INTO schema_migrations (version, name, checksum)
                       VALUES (%s, %s, %s);""",
                    (version, path.name, _checksum(sql)),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                logger.error(f"Migration {path.name} failed; rolled back")
                raise
        ran.append(version)

    if ran:
        logger.info(f"Applied {len(ran)} migration(s); schema at {max(ran)}")
    else:
        logger.info(f"Schema up to date at {current_version() or 'none'}")
    return ran

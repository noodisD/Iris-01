"""The migration runner.

The schema used to be built by CREATE TABLE IF NOT EXISTS, which can add a thing
and cannot change one: altering a CHECK, adding ON DELETE CASCADE to an existing
foreign key, or changing a column type were silent no-ops against a database
that already existed. A fresh database and a long-lived one could therefore
disagree with nothing to say so.

These tests are about the guarantees that replaces it with: a fresh database
ends up exactly where the snapshot says, applying twice does nothing, and
history that has changed underneath the database is an error rather than a
surprise.
"""

import json
from pathlib import Path

import psycopg2
import pytest

from agent import migrations
from agent.config import settings
from agent.database import db

from test_schema_snapshot import SNAPSHOT, _live_schema


def _scratch_database(name: str):
    """A genuinely empty database, dropped afterwards."""
    conn = psycopg2.connect(
        host=settings.POSTGRES_HOST, port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER, password=settings.POSTGRES_PASSWORD,
        dbname="postgres",
    )
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{name}";')
        cur.execute(f'CREATE DATABASE "{name}";')
    conn.close()


def _drop_database(name: str):
    conn = psycopg2.connect(
        host=settings.POSTGRES_HOST, port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER, password=settings.POSTGRES_PASSWORD,
        dbname="postgres",
    )
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{name}";')
    conn.close()


def test_migrations_are_discovered_in_numeric_order():
    found = migrations.discover()
    assert found, "there must be at least the initial migration"
    versions = [v for v, _ in found]
    assert versions == sorted(versions)
    assert versions[0] == "0001"


def test_a_fresh_database_ends_up_exactly_where_the_snapshot_says(setup_test_database):
    """The guarantee that makes migrations trustworthy: running them from empty
    reproduces the committed schema, so a new machine and an old one agree."""
    name = "iris_test_migration_scratch"
    _scratch_database(name)
    import agent.database as database_module
    saved_pool = database_module.db._pool
    saved_db = settings.POSTGRES_DB
    try:
        settings.POSTGRES_DB = name
        database_module.db._pool = None  # force a pool against the scratch database

        # Prove we are actually on the scratch database: if the pool had not
        # been rebuilt this would run against the suite's own database, which
        # already matches the snapshot, and the test would pass for free.
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT current_database();")
            assert cur.fetchone()[0] == name

        expected = [v for v, _ in migrations.discover()]
        assert migrations.upgrade() == expected, (
            "every migration on disk must apply to an empty database"
        )
        live = _live_schema()
    finally:
        # The scratch pool holds open connections; DROP DATABASE fails while
        # they exist, so close them before restoring the suite's own pool.
        if database_module.db._pool is not None and not database_module.db._pool.closed:
            database_module.db._pool.closeall()
        settings.POSTGRES_DB = saved_db
        database_module.db._pool = saved_pool
        _drop_database(name)

    want = json.loads(SNAPSHOT.read_text())
    for section in live:
        live[section].pop("schema_migrations", None)
        want[section].pop("schema_migrations", None)

    differences = [
        f"{section}.{table}.{key}"
        for section in ("columns", "constraints", "indexes")
        for table in set(live[section]) | set(want[section])
        for key in set(live[section].get(table, {})) | set(want[section].get(table, {}))
        if live[section].get(table, {}).get(key) != want[section].get(table, {}).get(key)
    ]
    assert differences == [], (
        "a database built purely from migrations does not match the committed "
        f"schema: {differences[:10]}"
    )


def test_applying_twice_applies_nothing(setup_test_database):
    assert migrations.upgrade() == [], "the suite's database is already migrated"
    assert migrations.current_version() == max(v for v, _ in migrations.discover())


def test_editing_an_applied_migration_is_an_error(setup_test_database, monkeypatch):
    """Editing a migration that has already run leaves existing databases on the
    old definition while new ones get the new one — the exact silent divergence
    migrations exist to prevent. It must fail loudly, not warn."""
    real = migrations.applied()
    tampered = {v: dict(d) for v, d in real.items()}
    tampered["0001"]["checksum"] = "0" * 64
    monkeypatch.setattr(migrations, "applied", lambda: tampered)

    with pytest.raises(migrations.MigrationError, match="has changed since it was applied"):
        migrations.upgrade()


def test_a_database_ahead_of_the_checkout_is_an_error(setup_test_database, monkeypatch):
    """Running old code against a newer database should say so."""
    ahead = dict(migrations.applied())
    ahead["9999"] = {"name": "9999_from_the_future.sql", "checksum": "x", "applied_at": None}
    monkeypatch.setattr(migrations, "applied", lambda: ahead)

    with pytest.raises(migrations.MigrationError, match="older than the database"):
        migrations.upgrade()


def test_a_misnamed_migration_is_rejected(tmp_path, monkeypatch):
    """Ordering is the whole contract, so a file that cannot be ordered is an
    error rather than something silently skipped or run last."""
    (tmp_path / "add_a_column.sql").write_text("SELECT 1;")
    monkeypatch.setattr(migrations, "MIGRATIONS_DIR", tmp_path)

    with pytest.raises(migrations.MigrationError, match="not a valid migration name"):
        migrations.discover()


def test_duplicate_migration_numbers_are_rejected(tmp_path, monkeypatch):
    (tmp_path / "0002_one.sql").write_text("SELECT 1;")
    (tmp_path / "0002_two.sql").write_text("SELECT 1;")
    monkeypatch.setattr(migrations, "MIGRATIONS_DIR", tmp_path)

    with pytest.raises(migrations.MigrationError, match="duplicate migration numbers"):
        migrations.discover()


def test_a_failing_migration_leaves_no_partial_state(setup_test_database, tmp_path, monkeypatch):
    """A migration is one transaction: if it fails halfway, nothing it did
    survives and it is not recorded as applied."""
    real_dir = migrations.MIGRATIONS_DIR
    for name in sorted(p.name for p in Path(real_dir).iterdir() if p.suffix == ".sql"):
        (tmp_path / name).write_text((Path(real_dir) / name).read_text())
    (tmp_path / "9001_half_broken.sql").write_text(
        "CREATE TABLE never_committed (id INT);\n"
        "CREATE TABLE never_committed (id INT);\n"  # duplicate: fails
    )
    monkeypatch.setattr(migrations, "MIGRATIONS_DIR", tmp_path)

    with pytest.raises(psycopg2.Error):
        migrations.upgrade()

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.never_committed');")
        assert cur.fetchone()[0] is None, "a failed migration must roll back"
    assert "9001" not in migrations.applied(), "a failed migration must not be recorded"

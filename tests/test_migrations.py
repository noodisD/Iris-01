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
from uuid import uuid4

import psycopg2
import pytest

from agent import migrations
from agent.config import settings
from agent.database import db

from test_schema_snapshot import SNAPSHOT, _live_schema

ROOT = Path(__file__).parent.parent


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


def test_a_missing_migrations_directory_is_an_error_not_an_empty_history(monkeypatch, tmp_path):
    """An installation that cannot migrate is not one with nothing to migrate.

    discover() returned [] when the directory was absent, so an installed copy
    without the SQL files would start and serve against whatever schema it
    found — the packaging mistake arriving later as a missing column.
    """
    monkeypatch.setattr(migrations, "MIGRATIONS_DIR", tmp_path / "nowhere")
    with pytest.raises(migrations.MigrationError, match="no migrations directory"):
        migrations.discover()


def test_the_recovery_a_migration_names_can_actually_be_carried_out():
    """Migration 0015 refuses to drop the legacy journal table while rows or
    references remain, and names the backfill script. That script moves rows
    and deliberately leaves the references, so on its own it could never
    satisfy the guard: the recovery path was a dead end. It has a --retire
    step now, and this keeps the two in step."""
    sql = (ROOT / "migrations" / "0015_retire_journal_entries.sql").read_text()
    assert "backfill_journal_entries.py" in sql
    script = (ROOT / "scripts" / "backfill_journal_entries.py").read_text()
    assert "--retire" in script, "the named script cannot satisfy the guard it is named in"
    for table in ("embeddings", "theme_occurrences", "processing_queue"):
        assert table in script, f"retiring must repoint {table} before the rows go"


def test_health_connect_migration_preserves_confirmed_evidence_and_pending_retry_keys(
        setup_test_database):
    sql = (ROOT / "migrations" / "0023_health_connect_source.sql").read_text()
    with db.connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO users (username) VALUES (%s) RETURNING id",
                            (f"migration_health_{uuid4().hex}",))
                user_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO themes (user_id, centroid_embedding, first_seen_at, last_seen_at) "
                    "VALUES (%s, (SELECT array_fill(0, ARRAY[1536])::vector), now(), now()) "
                    "RETURNING id", (user_id,))
                theme_id = cur.fetchone()[0]
                types = ("heart_rate", "sleep", "spo2")
                legacy_readings = [
                    {"source_type": f"fitbit_{kind}", "occurred_at": "2026-09-22",
                     "value_num": value, "payload_hash": f"old-{kind}"}
                    for kind, value in zip(types, (62, 420, 97), strict=True)
                ]
                cur.execute(
                    """INSERT INTO sensor_batches
                         (source, payload_path, status, parsed_payload, theme_links,
                          observation_count)
                       VALUES ('fitbit', 'intake:fitbit', 'confirmed', %s::jsonb, %s::jsonb, 3)
                       RETURNING id""",
                    (json.dumps({"source": "fitbit", "observations": legacy_readings}),
                     json.dumps({f"fitbit_{kind}": theme_id for kind in types})),
                )
                confirmed_id = cur.fetchone()[0]
                observation_ids = []
                for reading in legacy_readings:
                    cur.execute(
                        "INSERT INTO sensor_observations "
                        "(batch_id, source_type, payload_hash, value_num, occurred_at, occurred_date) "
                        "VALUES (%s, %s, %s, %s, '2026-09-22', '2026-09-22') RETURNING id",
                        (confirmed_id, reading["source_type"], reading["payload_hash"],
                         reading["value_num"]),
                    )
                    observation_ids.append(cur.fetchone()[0])
                cur.execute(
                    "INSERT INTO theme_occurrences "
                    "(theme_id, source_type, source_id, snippet, similarity_score, occurred_at) "
                    "VALUES (%s, 'fitbit_heart_rate', %s, '62 bpm', 1.0, '2026-09-22')",
                    (theme_id, observation_ids[0]),
                )
                cur.execute(
                    """INSERT INTO sensor_batches
                         (source, payload_path, status, review_day, parsed_payload,
                          observation_count, dropped_count)
                       VALUES ('fitbit', 'intake:fitbit', 'pending', '2026-09-24',
                               %s::jsonb, 1, 1) RETURNING id""",
                    (json.dumps({"source": "fitbit", "observations": [legacy_readings[0]]}),),
                )
                old_pending_id = cur.fetchone()[0]
                cur.execute(
                    """INSERT INTO sensor_batches
                         (source, payload_path, status, review_day, parsed_payload,
                          observation_count)
                       VALUES ('health_connect', 'intake:health_connect', 'pending',
                               '2026-09-24', %s::jsonb, 1) RETURNING id""",
                    (json.dumps({"source": "health_connect", "observations": [
                        {"source_type": "health_connect_sleep", "value_num": 400,
                         "payload_hash": "new-sleep"}]}),),
                )
                current_pending_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO sensor_deliveries (delivery_key, batch_id) VALUES (%s, %s)",
                    ("legacy-health-delivery", old_pending_id),
                )

                cur.execute(sql)

                cur.execute(
                    "SELECT source, payload_path, parsed_payload, theme_links "
                    "FROM sensor_batches WHERE id = %s", (confirmed_id,))
                source, path, parsed, links = cur.fetchone()
                assert (source, path) == ("health_connect", "intake:health_connect")
                assert parsed["source"] == "health_connect"
                assert [row["source_type"] for row in parsed["observations"]] == [
                    f"health_connect_{kind}" for kind in types
                ]
                assert links == {f"health_connect_{kind}": theme_id for kind in types}
                cur.execute(
                    "SELECT id, source_type FROM sensor_observations WHERE batch_id = %s ORDER BY id",
                    (confirmed_id,),
                )
                assert cur.fetchall() == list(zip(
                    observation_ids, (f"health_connect_{kind}" for kind in types), strict=True))
                cur.execute(
                    "SELECT t.source_type, s.source_type, t.snippet FROM theme_occurrences t "
                    "JOIN sensor_observations s ON s.id = t.source_id "
                    "AND s.source_type = t.source_type WHERE t.theme_id = %s", (theme_id,))
                assert cur.fetchall() == [
                    ("health_connect_heart_rate", "health_connect_heart_rate", "62 bpm"),
                ]
                cur.execute(
                    "SELECT source, parsed_payload, observation_count, dropped_count "
                    "FROM sensor_batches WHERE id = %s", (current_pending_id,))
                source, parsed, count, dropped = cur.fetchone()
                assert (source, count, dropped) == ("health_connect", 2, 1)
                assert [row["source_type"] for row in parsed["observations"]] == [
                    "health_connect_heart_rate", "health_connect_sleep",
                ]
                cur.execute("SELECT count(*) FROM sensor_batches WHERE id = %s",
                            (old_pending_id,))
                assert cur.fetchone()[0] == 0
                cur.execute("SELECT batch_id FROM sensor_deliveries WHERE delivery_key = %s",
                            ("legacy-health-delivery",))
                assert cur.fetchone()[0] == current_pending_id
        finally:
            conn.rollback()


def test_the_markets_rename_moves_ideas_already_filed_under_the_old_name(test_user):
    """0028 must work on a database that already has ideas in the renamed area.

    The suite runs on an empty test database, where 0028's update moves nothing,
    so the suite passed while 0028 failed on real data: it moved the rows before
    lifting the old rule, which does not admit the new name. This rebuilds 0027's
    rule, files one idea under the old name, runs 0028 over it and rolls all of it
    back. The old name is read from 0027 rather than written here.
    """
    import re
    old_rule = (ROOT / "migrations" / "0027_learning_domain.sql").read_text()
    kept = {"philosophy", "economics", "politics", "ethics", "learning", "other"}
    old_area = next(a for a in re.findall(r"'([a-z]+)'", old_rule) if a not in kept)
    rename = (ROOT / "migrations" / "0028_markets_domain.sql").read_text()

    with db.connection() as conn, conn.cursor() as cur:
        try:
            cur.execute(old_rule)  # the rule as it stood before 0028
            cur.execute(
                """INSERT INTO ideas (user_id, statement, statement_key, domain)
                   VALUES (%s, %s, %s, %s) RETURNING id""",
                (test_user["id"], "Buy the dip only with a written exit.", "0" * 64, old_area))
            idea_id = cur.fetchone()[0]
            cur.execute(rename)
            cur.execute("SELECT domain FROM ideas WHERE id = %s", (idea_id,))
            assert cur.fetchone()[0] == "markets"
        finally:
            conn.rollback()

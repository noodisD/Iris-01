"""The one-way cutover preserves saved opinions, never copied journal passages."""
from __future__ import annotations

from uuid import uuid4

import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json

from agent.config import settings
from agent.migrations import discover


def test_legacy_feedback_is_archived_before_old_derived_tables_are_dropped():
    name = f"iris_personal_migration_test_{uuid4().hex[:10]}"
    config = {"user": settings.POSTGRES_USER, "password": settings.POSTGRES_PASSWORD,
              "host": settings.POSTGRES_HOST, "port": settings.POSTGRES_PORT}
    admin = psycopg2.connect(dbname="postgres", **config)
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        conn = psycopg2.connect(dbname=name, **config)
        try:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION vector")
            conn.commit()
            migrations = discover()
            for version, path in migrations:
                if version == "0045":
                    break
                with conn.cursor() as cur:
                    cur.execute(path.read_text(encoding="utf-8"))
                conn.commit()
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO users (username, password_hash)
                               VALUES ('legacy_owner', 'test') RETURNING id""")
                owner = cur.fetchone()[0]
                cur.execute("""INSERT INTO reflections (user_id, reflection_date, content)
                               VALUES (%s, '2026-09-01', %s) RETURNING id""",
                            (owner, "The owner's original private journal passage."))
                source = cur.fetchone()[0]
                cite = [{"entryId": str(source), "sourceType": "reflection",
                         "entryDate": "2026-09-01", "text": "The owner's original private journal passage."}]
                cur.execute("""INSERT INTO occasions
                               (user_id, fingerprint, actor, modality, situation,
                                response, citations)
                               VALUES (%s, %s, 'self', 'happened', 'Situation', 'Response', %s)
                               RETURNING id""", (owner, "a" * 64, Json(cite)))
                occasion = cur.fetchone()[0]
                cur.execute("""INSERT INTO pattern_labels
                               (occasion_id, pattern_id, tone, owner_tone, verdict_note)
                               VALUES (%s, 'old_label', 'better', 'mixed', 'Owner note')""",
                            (occasion,))
                cur.execute("""INSERT INTO pattern_verdicts
                               (user_id, pattern_id, verdict, note)
                               VALUES (%s, 'old_label', NULL, 'General note')""", (owner,))
                cur.execute("""INSERT INTO difference_verdicts
                               (user_id, pattern_id, other_pattern_id, verdict, note)
                               VALUES (%s, 'old_label', 'other_label', 'rings_true', 'Pair note')""",
                            (owner,))
            conn.commit()
            # The seeded v44 occasion needs its 0044 source linkage, which was
            # created when earlier migrations ran against an empty archive.
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO occasion_sources
                               (occasion_id, reflection_id, source_revision)
                               VALUES (%s, %s, 1)""", (occasion, source))
            conn.commit()
            path = next(p for version, p in migrations if version == "0045")
            with conn.cursor() as cur:
                cur.execute(path.read_text(encoding="utf-8"))
            conn.commit()
            with conn.cursor() as cur:
                cur.execute("""SELECT kind, source_ids, payload FROM discovery_legacy_feedback
                               WHERE user_id = %s ORDER BY kind""", (owner,))
                archived = {kind: (ids, payload) for kind, ids, payload in cur.fetchall()}
                assert set(archived) == {"occasion", "pattern", "ordered_pair"}
                assert all(ids == [source] for ids, _ in archived.values())
                assert archived["occasion"][1]["ownerTone"] == "mixed"
                assert archived["occasion"][1]["verdictNote"] == "Owner note"
                assert archived["pattern"][1]["note"] == "General note"
                assert archived["ordered_pair"][1]["note"] == "Pair note"
                assert all("private journal passage" not in str(payload)
                           for _, payload in archived.values())
                cur.execute("SELECT to_regclass('public.occasions'), to_regclass('public.day_difference_verdicts')")
                assert cur.fetchone() == (None, "day_difference_verdicts")
        finally:
            conn.close()
    finally:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                sql.Identifier(name)))
        admin.close()

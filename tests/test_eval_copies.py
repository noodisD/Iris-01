"""The with-and-without-history test: the "direct" copy must hold nothing learnt
from the imported archive, and keep everything the owner gave IRIS directly.

Fixtures are invented and neutral.
"""

from __future__ import annotations

import asyncio
import importlib.util
from datetime import date
from pathlib import Path

import httpx

from agent import discovery
from agent.config import settings
from agent.database import db
from agent.episodes import Episode
from agent.observations import Citation
from agent.reference_evaluation import account_fingerprint
from agent.eval_copies import prune_to_direct
from agent.importing import store
from agent.trackers.reflections import ReflectionService
from iris_api import app, get_current_user_id

VECTOR = "[" + ",".join(["0.01"] * 1536) + "]"


def _embed(cur, source_type, source_id):
    cur.execute("INSERT INTO embeddings (source_type, source_id, model_name, vector) VALUES (%s, %s, 'test', %s::vector)",
                (source_type, source_id, VECTOR))


def _idea(cur, user_id, statement, reflection_id):
    cur.execute("""INSERT INTO ideas (user_id, statement, statement_key, domain, status)
                   VALUES (%s, %s, md5(%s) || md5(%s), 'other', 'active') RETURNING id""",
                (user_id, statement, statement, statement))
    idea = cur.fetchone()[0]
    cur.execute("""INSERT INTO idea_citations (idea_id, reflection_id, quote, quote_hash, source_hash, stance, status)
                   VALUES (%s, %s, 'a quote', md5('q') || md5('q'), md5('s') || md5('s'), 'endorsed', 'accepted')""",
                (idea, reflection_id))
    return idea


def _account(reflection_id: int, day: date, text: str) -> dict:
    return Episode(actor="self", record_kind="self_report", situation=None, response=None,
                   demand=None, information=None, feeling=None, concern=None,
                   immediate_outcome=None, later_outcome=None, explanation=None,
                   self_report=text, domain=None, recorded_on=day,
                   citations=(Citation(reflection_id, day, text),)).as_dict()


def test_the_direct_copy_keeps_what_was_given_directly_and_nothing_from_the_archive(test_user):
    uid = test_user["id"]
    reflections = ReflectionService(uid)
    written = reflections.create_reflection(content="Walked to the allotment and planted beans.",
                                            reflection_date=date(2026, 9, 20))
    imported = db.create_reflection(uid, "An old note about repotting the fig.", reflection_date=date(2024, 5, 1),
                                    source="import")
    batch = store.create_batch(uid, "text", "export.zip", None)
    store.replace_items(batch, uid, [{"source_name": "old.md", "content": "An old note", "content_hash": "0" * 64,
                                      "entry_date": date(2024, 5, 1)}])
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE import_items SET reflection_id = %s WHERE batch_id = %s", (imported, batch))
        _embed(cur, "reflection", written)
        _embed(cur, "reflection", imported)
        kept_idea = _idea(cur, uid, "Beans like the sun.", written)
        archive_idea = _idea(cur, uid, "Figs need repotting in spring.", imported)
        direct = _account(written, date(2026, 9, 20), "Walked to the allotment and planted beans.")
        historical = _account(imported, date(2024, 5, 1), "An old note about repotting the fig.")
        for source, account in ((written, direct), (imported, historical)):
            discovery._store_reading(cur, uid, [account], source_revisions={source: 1})
        cur.execute("""INSERT INTO discovery_views
                       (user_id, range, source_generation, review_generation, manifest_hash,
                        as_of, interpretation_version, library_hash, model, payload, completed_at)
                       SELECT %s, 'all', source_generation, review_generation, %s, CURRENT_DATE,
                              %s, %s, 'synthetic', %s::jsonb, NOW()
                         FROM discovery_state WHERE user_id = %s""",
                    (uid, "a" * 64, "b" * 64, "c" * 64,
                     '{"archivedPhrase":"repotting the fig"}', uid))
        cur.execute("""INSERT INTO conversation_messages (user_id, session_id, role, content) VALUES
                       (%s, 's1', 'user', 'How are the beans?'), (%s, 's1', 'assistant', 'Like the fig in 2024.')""",
                    (uid, uid))
        conn.commit()

        counts = prune_to_direct(cur)
        conn.commit()

        cur.execute("SELECT id FROM reflections WHERE user_id = %s ORDER BY id", (uid,))
        assert [r[0] for r in cur.fetchall()] == [written]
        cur.execute("SELECT source_id FROM embeddings WHERE source_type = 'reflection' AND source_id IN (%s, %s)",
                    (written, imported))
        assert [r[0] for r in cur.fetchall()] == [written]
        cur.execute("SELECT id, status FROM ideas WHERE id IN (%s, %s) ORDER BY id", (kept_idea, archive_idea))
        assert dict(cur.fetchall()) == {kept_idea: "active", archive_idea: "rejected"}
        cur.execute("SELECT id, reflection_id FROM discovery_accounts WHERE user_id = %s", (uid,))
        assert cur.fetchall() == [(account_fingerprint(direct), written)]
        cur.execute("SELECT reflection_id FROM discovery_reads WHERE reflection_id IN (%s, %s)",
                    (written, imported))
        assert cur.fetchall() == [(written,)]
        cur.execute("SELECT count(*) FROM discovery_views WHERE user_id = %s", (uid,))
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT role FROM conversation_messages WHERE user_id = %s", (uid,))
        assert [r[0] for r in cur.fetchall()] == ["user"], "IRIS's replies were written with the archive in view"
        cur.execute("SELECT count(*) FROM import_batches WHERE user_id = %s", (uid,))
        assert cur.fetchone()[0] == 0
    assert counts["entries"] >= 1


def test_a_comparison_question_is_answered_and_its_test_chat_removed(test_user, mock_llm):
    """The comparison asks through the ordinary chat route, then deletes that
    chat from the copy, so one question never colours the next."""
    spec = importlib.util.spec_from_file_location(
        "eval_compare", Path(__file__).resolve().parent.parent / "scripts" / "eval_compare.py")
    compare = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compare)

    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    try:
        async def exercise():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
                return await compare._ask(client, "http://127.0.0.1", settings.POSTGRES_DB, "How are the beans?")
        answer = asyncio.run(exercise())
    finally:
        app.dependency_overrides.clear()

    assert answer == "IRIS Mocked Response"
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM conversation_messages WHERE user_id = %s", (test_user["id"],))
        assert cur.fetchone()[0] == 0, "the test chat is gone from the copy"

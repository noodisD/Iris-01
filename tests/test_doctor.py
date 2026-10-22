"""The doctor catches what it promises to catch, and never repeats what anyone wrote.

Every entry below is invented. Checks look at the whole test database, so each
test compares a check's value before and after breaking one promise.
"""

from __future__ import annotations

import json
import re

import pytest

from agent import doctor
from agent.database import db
from agent.doctor import checks_moving, checks_quality

SECRET = "the lighthouse keeper painted every third step a different shade of blue"


@pytest.fixture(autouse=True)
def no_live_server(monkeypatch):
    """The real IRIS may be running on this machine; tests never ask it anything."""
    monkeypatch.setattr(checks_moving, "SERVER", "http://127.0.0.1:9")


def _one(check_id: str) -> dict:
    return next(r for r in doctor.run({check_id}) if r["id"] == check_id)


def test_an_embedding_left_behind_by_a_delete_is_found(test_user):
    before = _one("data.orphan_embeddings")["value"]
    gone = db.create_reflection(test_user["id"], "A note that will be deleted.")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM reflections WHERE id = %s", (gone,))
        cur.execute("INSERT INTO embeddings (source_type, source_id, model_name, vector) VALUES "
                    "('reflection', %s, 'text-embedding-3-small', %s)", (gone, [0.1] * 1536))
        conn.commit()
    after = _one("data.orphan_embeddings")
    assert after["status"] == "fail" and after["value"] == before + 1
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM embeddings WHERE source_type = 'reflection' AND source_id = %s", (gone,))
        conn.commit()


def test_a_reading_copy_that_drifted_is_found(test_user):
    before = _one("data.reading_copies")["value"]
    rid = db.create_reflection(test_user["id"], "so i went to the market and bought pears")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE reflections SET reading_copy = %s WHERE id = %s",
                    ("So I went to the market and bought apples.", rid))
        conn.commit()
    after = _one("data.reading_copies")
    assert after["status"] == "fail" and after["value"] == before + 1 and rid in after["details"]["ids"]


def test_a_job_that_gave_up_is_found_by_kind_without_its_message(test_user):
    from agent.work_queue import MAX_ATTEMPTS

    rid = db.create_reflection(test_user["id"], SECRET)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO processing_queue (user_id, source_type, source_id, attempts, last_error)
                       VALUES (%s, 'discovery', %s, %s, %s)
                       ON CONFLICT (source_type, source_id) DO UPDATE
                          SET attempts = EXCLUDED.attempts, last_error = EXCLUDED.last_error""",
                    (test_user["id"], rid, MAX_ATTEMPTS, f"invalid_read_store (ValueError: {SECRET})"))
        conn.commit()
    result = _one("queue.exhausted")
    assert result["status"] == "fail" and "discovery: invalid_read_store" in result["details"]["kinds"]
    assert SECRET not in json.dumps(result)


def test_a_search_that_misses_memories_fails(test_user, monkeypatch):
    import random

    rng = random.Random(11)
    # Distinct vectors: repeated ones tie, and the exact top ten would depend on tie-breaking.
    for n in range(40):
        rid = db.create_reflection(test_user["id"], f"Invented note {n}.")
        db.add_embedding("reflection", rid, "text-embedding-3-small", [rng.uniform(-1, 1) for _ in range(1536)])
    monkeypatch.setattr(checks_quality, "_owner", lambda: test_user["id"])
    assert _one("retrieval.complete")["status"] == "ok"
    monkeypatch.setattr(db, "search_similar_embeddings", lambda *a, **k: [])
    failing = _one("retrieval.complete")
    assert failing["status"] == "fail" and failing["value"] == 0


def test_a_new_failure_is_new_then_resolved(test_user, monkeypatch):
    from agent.doctor import Result

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM health_checks WHERE check_id = 'test.flip'")
        conn.commit()
    state = {"status": "fail"}
    monkeypatch.setattr(doctor, "CHECKS", [doctor.Check(
        "test.flip", "test", lambda: Result("test.flip", state["status"], "Flips.", value=1))])
    monkeypatch.setattr(doctor, "_load", lambda: None)
    first = doctor.run()
    assert [c["change"] for c in doctor.changes(first, doctor.store(first))] == ["NEW"]
    state["status"] = "ok"
    second = doctor.run()
    diff = doctor.changes(second, doctor.store(second))
    assert [c["change"] for c in diff] == ["RESOLVED"]
    assert "RESOLVED  test.flip" in doctor.report(second, diff)


def test_no_check_repeats_what_anyone_wrote(test_user):
    db.create_reflection(test_user["id"], SECRET)
    results = doctor.run({"data", "moving", "owner", "resources", "docs"})
    text = json.dumps(results, default=str) + doctor.report(results, [])
    words = re.findall(r"[a-z']+", SECRET)
    runs = {" ".join(words[i:i + 5]) for i in range(len(words) - 4)}
    assert not any(run in text.lower() for run in runs)


def test_a_restart_is_refused_while_a_pattern_update_runs(monkeypatch):
    from agent.doctor.__main__ import can_restart

    monkeypatch.setattr(checks_moving, "_worker",
                        lambda: {"alive": True, "current": {"source_type": "personal_dynamics"}})
    ok, why = can_restart()
    assert not ok and "pattern update" in why
    monkeypatch.setattr(checks_moving, "_worker", lambda: {"alive": True, "current": None})
    assert can_restart()[0]


def test_every_check_has_a_runbook():
    from pathlib import Path

    doctor._load()
    missing = [c.id for c in doctor.CHECKS if not (Path("docs/runbooks") / f"{c.id}.md").exists()]
    assert missing == []


def test_docs_coverage_finds_unnamed_modules_and_missing_paths(tmp_path):
    from agent.doctor.checks_docs import scan

    (tmp_path / "agent" / "tools").mkdir(parents=True)
    for name in ("named.py", "forgotten.py", "tools/inner.py"):
        (tmp_path / "agent" / name).write_text("")
    (tmp_path / "ARCHITECTURE.md").write_text("Uses `named.py` and `tools/*`; see `agent/gone.py`, `migrations/NNNN_*.sql`.")
    (tmp_path / "migrations").mkdir()
    (tmp_path / "migrations" / "0001_start.sql").write_text("")
    unnamed, broken = scan(tmp_path)
    assert unnamed == ["forgotten.py"]
    assert broken == ["ARCHITECTURE.md: agent/gone.py"]


# --- step 2: what waits on the owner, room and money --------------------------------

def test_owner_items_are_waiting_not_failures(monkeypatch):
    from datetime import UTC, datetime, timedelta

    from agent.doctor import checks_owner

    old = datetime.now(UTC) - timedelta(days=12)
    answers = iter([(3, old, 4200)])
    monkeypatch.setattr(checks_owner, "_one", lambda sql, *a: next(answers))
    batches = checks_owner.sensor_batches()
    assert batches.status == "waiting" and batches.value == 3 and "oldest 12 days" in batches.summary
    replies = iter([(1,), (datetime.now(UTC) - timedelta(days=5),)])
    monkeypatch.setattr(checks_owner, "_one", lambda sql, *a: next(replies))
    assert checks_owner.phone_silent().status == "waiting"
    replies = iter([(0,)])
    monkeypatch.setattr(checks_owner, "_one", lambda sql, *a: next(replies))
    assert checks_owner.phone_silent().status == "ok"


def test_spend_over_the_weekly_budget_warns(monkeypatch):
    from agent.doctor import checks_resources

    monkeypatch.setattr(checks_resources.settings, "WEEKLY_BUDGET_USD", 0.5)
    monkeypatch.setattr(checks_resources, "_rows", lambda sql, *a: [(True, "chat", 0.1), (False, "queue.x", 0.6)])
    over = checks_resources.spend()
    assert over.status == "warn" and over.value == 0.7 and "budget $0.50 a week" in over.summary
    monkeypatch.setattr(checks_resources, "_rows", lambda sql, *a: [(True, "chat", 0.05), (False, "chat", 0.3)])
    assert checks_resources.spend().status == "ok"


def test_a_model_call_from_a_worker_thread_is_named_for_its_job(monkeypatch):
    from agent import work_queue
    from agent.observability import llm

    class DbSpan:
        name = "db.connection"
        attributes = {"iris.component": "db"}
    monkeypatch.setattr(llm.trace, "get_current_span", lambda: DbSpan())
    monkeypatch.setattr(work_queue, "_current", {"source_type": "personal_dynamics"})
    assert llm._purpose(None) == "queue.personal_dynamics"
    monkeypatch.setattr(work_queue, "_current", None)
    assert llm._purpose(None) == "background"
    assert llm._purpose("chat.reply") == "chat.reply"


def test_hours_thrown_away_by_failed_attempts_warn(monkeypatch):
    from agent.doctor import checks_resources

    monkeypatch.setattr(checks_resources, "_rows", lambda sql, *a: [("personal_dynamics", 3, 1287.0)])
    result = checks_resources.wasted()
    assert result.status == "warn" and "21.4 h" in result.summary and "personal_dynamics" in result.summary


def test_a_new_kind_of_error_is_flagged_and_a_known_one_is_not(monkeypatch):
    from agent.doctor import checks_resources

    monkeypatch.setattr(checks_resources, "_rows", lambda sql, *a: [
        ("llm.chat", "openai.RateLimitError", True), ("llm.chat", "openai.RateLimitError", False),
        ("queue.job", "ValueError", True)])
    result = checks_resources.new_error_kinds()
    assert result.status == "warn" and list(result.details["new"]) == ["queue.job: ValueError"]


def test_backups_old_or_missing_warn(tmp_path, monkeypatch):
    import os
    import time

    from agent.doctor import checks_resources

    monkeypatch.setattr(checks_resources, "BACKUPS", tmp_path)
    assert checks_resources.backups().status == "warn"
    dump = tmp_path / "iris_db_x.dump"
    dump.write_bytes(b"0" * 10)
    assert checks_resources.backups().status == "ok"
    week_ago = time.time() - 9 * 86400
    os.utime(dump, (week_ago, week_ago))
    assert checks_resources.backups().status == "warn"


def test_the_banner_reads_the_last_stored_run(test_user, monkeypatch):
    from fastapi.testclient import TestClient

    from agent.doctor import Result
    from iris_api import app

    monkeypatch.setattr(doctor, "CHECKS", [
        doctor.Check("test.banner_fail", "test", lambda: Result("test.banner_fail", "fail", "Something broke.")),
        doctor.Check("test.banner_ok", "test", lambda: Result("test.banner_ok", "ok", "Fine."))])
    monkeypatch.setattr(doctor, "_load", lambda: None)
    run_id = doctor.store(doctor.run())
    latest = TestClient(app).get("/api/health/latest").json()
    assert latest["runId"] == run_id
    assert latest["attention"] == [{"id": "test.banner_fail", "status": "fail", "summary": "Something broke."}]
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM health_checks WHERE run_id = %s", (run_id,))
        conn.commit()


def _job_spans(source_type: str, mode: str | None, minutes: list[float]) -> list[str]:
    import uuid

    from psycopg2.extras import Json

    ids = []
    with db.connection() as conn, conn.cursor() as cur:
        for m in minutes:
            span = uuid.uuid4().hex[:16]
            attributes = {"iris.queue.source_type": source_type, "iris.queue.outcome": "retired",
                          **({"iris.queue.mode": mode} if mode else {})}
            cur.execute("""INSERT INTO obs_spans (trace_id, span_id, name, component, kind, is_entry, started_at,
                                                  duration_ms, self_ms, status, attributes, module_id)
                           VALUES (%s, %s, 'queue.job', 'queue', 'consumer', TRUE, NOW() - interval '1 hour',
                                   %s, %s, 'ok', %s, 'queue.job')""",
                        (uuid.uuid4().hex, span, m * 60000, m * 60000, Json(attributes)))
            ids.append(span)
        conn.commit()
    return ids


def test_a_pattern_update_is_judged_against_runs_of_its_own_kind():
    from agent.doctor.checks_moving import _limit

    spans = _job_spans("personal_dynamics", "update", [10, 12, 11, 9, 10]) + \
        _job_spans("personal_dynamics", "rebuild", [200, 220, 210, 190, 205])
    try:
        update, why = _limit("personal_dynamics", "update")
        rebuild, _ = _limit("personal_dynamics", "rebuild")
        assert 25 <= update <= 40 and "update" in why, "about three times a usual update"
        assert 550 <= rebuild <= 700
        assert _limit("personal_dynamics")[0] >= 550, "without a mode, learned time only raises"
    finally:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM obs_spans WHERE span_id = ANY(%s)", (spans,))
            conn.commit()


def test_a_job_can_say_which_kind_of_run_it_is(monkeypatch):
    from agent import work_queue

    monkeypatch.setattr(work_queue, "_current", {"source_type": "personal_dynamics"})
    work_queue.note_mode("rebuild")
    assert work_queue.current_item()["mode"] == "rebuild"
    monkeypatch.setattr(work_queue, "_current", None)
    work_queue.note_mode("update")  # outside a job: nothing to record


# --- step 3: safe-auto repairs ----------------------------------------------------------

@pytest.fixture
def no_real_backup(monkeypatch):
    from agent.doctor import fixes

    taken = []
    monkeypatch.setattr(fixes, "take_backup", lambda: taken.append(1) or ("Took a backup.", {}))
    return taken


def _failing(check_id: str) -> list[dict]:
    return [r for r in doctor.run({check_id}) if r["id"] == check_id]


def test_orphaned_vectors_are_deleted_after_a_backup_and_rechecked(test_user, no_real_backup):
    from agent.doctor import fixes

    gone = db.create_reflection(test_user["id"], "A note that will be deleted.")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM reflections WHERE id = %s", (gone,))
        cur.execute("INSERT INTO embeddings (source_type, source_id, model_name, vector) VALUES "
                    "('reflection', %s, 'text-embedding-3-small', %s)", (gone, [0.1] * 1536))
        conn.commit()
    repaired = fixes.apply(_failing("data.orphan_embeddings"), None)
    assert [(r["id"], r["outcome"]) for r in repaired] == [("data.orphan_embeddings", "fixed")]
    assert no_real_backup == [1], "a repair that writes data is preceded by a backup"
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT outcome FROM health_fixes WHERE check_id = 'data.orphan_embeddings' "
                    "ORDER BY fixed_at DESC LIMIT 1")
        assert cur.fetchone()[0] == "fixed"


def test_a_drifted_reading_copy_is_cleared(test_user, no_real_backup):
    from agent.doctor import fixes

    rid = db.create_reflection(test_user["id"], "so i went to the market and bought pears")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE reflections SET reading_copy = 'So I went to the market and bought apples.' "
                    "WHERE id = %s", (rid,))
        conn.commit()
    repaired = fixes.apply(_failing("data.reading_copies"), None)
    assert repaired[0]["outcome"] == "fixed" and rid in repaired[0]["details"]["ids"]


def test_a_cheap_failed_job_is_requeued_once_and_a_costly_one_is_left(test_user, no_real_backup):
    from agent.doctor import fixes
    from agent.work_queue import MAX_ATTEMPTS

    rid = db.create_reflection(test_user["id"], "An invented entry.")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM health_fixes WHERE check_id = 'queue.exhausted'")
        for kind, sid in (("discovery", rid), ("personal_dynamics", test_user["id"])):
            cur.execute("""INSERT INTO processing_queue (user_id, source_type, source_id, attempts, last_error)
                           VALUES (%s, %s, %s, %s, 'provider_failure')
                           ON CONFLICT (source_type, source_id) DO UPDATE
                              SET attempts = EXCLUDED.attempts, last_error = EXCLUDED.last_error""",
                        (test_user["id"], kind, sid, MAX_ATTEMPTS))
        conn.commit()
    first = fixes.apply(_failing("queue.exhausted"), None)[0]
    assert ["discovery", rid] in first["details"]["requeued"]
    assert ["personal_dynamics", test_user["id"]] in first["details"]["left"]
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE processing_queue SET attempts = %s WHERE source_type = 'discovery' AND source_id = %s",
                    (MAX_ATTEMPTS, rid))
        conn.commit()
    again = fixes.apply(_failing("queue.exhausted"), None)[0]
    assert ["discovery", rid] in again["details"]["left"], "re-queued once a week, not every morning"


def test_nothing_is_repaired_without_a_backup_first(test_user, monkeypatch):
    from agent.doctor import fixes

    def broken():
        raise RuntimeError("disk full")
    monkeypatch.setattr(fixes, "take_backup", broken)
    gone = db.create_reflection(test_user["id"], "Another note to delete.")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM reflections WHERE id = %s", (gone,))
        cur.execute("INSERT INTO embeddings (source_type, source_id, model_name, vector) VALUES "
                    "('reflection', %s, 'text-embedding-3-small', %s)", (gone, [0.1] * 1536))
        conn.commit()
    repaired = fixes.apply(_failing("data.orphan_embeddings"), None)
    assert repaired[0]["outcome"] == "failed"
    assert _failing("data.orphan_embeddings")[0]["status"] == "fail", "left as it was"
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM embeddings WHERE source_type = 'reflection' AND source_id = %s", (gone,))
        conn.commit()


def test_only_safe_auto_checks_with_a_repair_are_touched(no_real_backup, monkeypatch):
    from agent.doctor import fixes

    called = []
    monkeypatch.setitem(fixes.FIXERS, "test.owner_only", (lambda: called.append(1) or ("x", {}), True))
    results = [{"id": "test.owner_only", "status": "fail", "action_class": "needs-owner", "value": 1},
               {"id": "data.quotes", "status": "fail", "action_class": "needs-owner", "value": 1}]
    assert fixes.apply(results, None) == [] and called == [] and no_real_backup == []

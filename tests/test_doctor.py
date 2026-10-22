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
    for n in range(40):
        rid = db.create_reflection(test_user["id"], f"Invented note {n}.")
        db.add_embedding("reflection", rid, "text-embedding-3-small",
                         [((n * 7 + i) % 13) / 13 - 0.5 for i in range(1536)])
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
    results = doctor.run({"data", "moving"})
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

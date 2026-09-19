"""What happens between a write and the evidence it becomes — and at startup.

ADR-0011 made ingestion a durable queue. The review found the seams it left,
each of which let the journal and the engines quietly disagree:

- the job was queued on a second connection after the entry committed, with
  its failure swallowed, so a crash between them left an entry no engine would
  ever see;
- a job whose source could not be found was retired as a success;
- an edit that arrived while the old text was being processed was dropped;
- a deleted entry left its job behind;
- only imports woke the worker, so everything else waited for the next poll;
- the HTTP process started serving past a failed migration.

Every entry below is invented.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg2
import pytest

from agent import work_queue
from agent.database import db
from agent.trackers.reflections import ReflectionService


def _queued(source_type, source_id):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT attempts, last_error, generation FROM processing_queue
                        WHERE source_type = %s AND source_id = %s;""",
                    (source_type, source_id))
        return cur.fetchone()


def _reflection_count(user_id):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM reflections WHERE user_id = %s;", (user_id,))
        return cur.fetchone()[0]


# --- the entry and its job are one write -----------------------------------------

def test_an_entry_and_its_job_commit_together(test_user, monkeypatch):
    """The job used to be written after the entry had committed, on its own
    connection, and a failure there was logged and swallowed: the journal showed
    the entry and every engine was blind to it, with nothing left to say so."""
    def unavailable(cur, *args):
        raise psycopg2.OperationalError("queue unavailable")
    monkeypatch.setattr(type(db), "_queue", staticmethod(unavailable))

    with pytest.raises(psycopg2.OperationalError):
        ReflectionService(test_user["id"]).create_reflection(content="Walked to the lake.")

    assert _reflection_count(test_user["id"]) == 0, "no entry without its job"


def test_every_write_asks_the_worker_to_look(test_user, monkeypatch):
    """Only imports and recordings woke it; a habit tick waited for the poll."""
    from agent.memory import ConversationMemory
    from agent.trackers.habits import HabitTracker

    woken = []
    monkeypatch.setattr(work_queue.worker, "wake", lambda: woken.append(True))
    uid = test_user["id"]

    ReflectionService(uid).create_reflection(content="Slept well for once.")
    tracker = HabitTracker(uid)
    habit_id = tracker.create_habit("Evening walk")
    tracker.log_completion(habit_id)
    ConversationMemory(uid, "session").add_message("user", "hello")

    assert len(woken) == 4


# --- an edit that lands mid-run is not lost ------------------------------------------

def test_an_edit_made_while_the_old_text_is_processed_is_not_lost(test_user, monkeypatch):
    """Re-queueing an entry already in flight did nothing, and the run in flight
    finished with the old words and retired the job. The correction was never
    processed: the journal showed it while every engine held the original."""
    import agent.pipeline as pipeline

    service = ReflectionService(test_user["id"])
    rid = service.create_reflection(content="The first version of the entry.")
    embedded = []
    real = pipeline.generate_embedding

    def embed(text, model=None):
        embedded.append(text)
        if len(embedded) == 1:  # the owner edits while the first run is embedding
            service.update_reflection(rid, content="The corrected version of the entry.")
        return real(text, model=model)

    monkeypatch.setattr(pipeline, "generate_embedding", embed)
    work_queue.drain()

    assert any("corrected version" in t for t in embedded), "the edit was processed"
    assert _queued("reflection", rid) is None, "and nothing is left waiting"
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT COUNT(*) FROM embeddings
                        WHERE source_type = 'reflection' AND source_id = %s;""", (rid,))
        assert cur.fetchone()[0] == 1


# --- a job that cannot run is not a success ------------------------------------------

def test_a_missing_source_is_a_failure_not_a_success(test_user):
    """The pipeline logged and returned, and the queue deleted the job as done."""
    work_queue.enqueue("reflection", 987_654, test_user["id"])

    succeeded, failed = work_queue.process_due()

    assert (succeeded, failed) == (0, 1)
    attempts, last_error, _ = _queued("reflection", 987_654)
    assert "could not be found" in last_error


def test_a_deleted_entry_takes_its_job_and_its_counts_with_it(test_user):
    """Otherwise the job fails as missing — correctly, now — for an entry the
    owner deleted on purpose; and the theme kept counting it."""
    service = ReflectionService(test_user["id"])
    rid = service.create_reflection(content="Something I will delete.")
    theme_id = db.create_theme(test_user["id"], [0.1] * 1536, "a theme",
                               datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat())
    db.add_theme_occurrence(theme_id, "reflection", rid, "x", 0.9,
                            (datetime.now(UTC) - timedelta(days=3)).isoformat())
    db.update_theme_stats(theme_id)
    assert _queued("reflection", rid) is not None, "precondition: queued"

    service.delete_reflection(rid)

    assert _queued("reflection", rid) is None
    assert db.get_theme_by_id(theme_id)["occurrence_count"] == 0


# --- starting up ------------------------------------------------------------------------

def test_a_failed_migration_stops_the_api_starting(monkeypatch):
    """It was logged, and the process served — and started the worker — against a
    schema it did not expect. The CLI already refused; the HTTP door now does."""
    from fastapi.testclient import TestClient

    import iris_api

    def broken():
        raise RuntimeError("migration 9999 failed")
    monkeypatch.setattr(iris_api.migrations, "upgrade", broken)

    with pytest.raises(RuntimeError, match="9999"):
        with TestClient(iris_api.app):
            pass


def test_a_failed_import_stops_it_too(monkeypatch):
    """Every data route would otherwise raise NameError on its first request
    while the health check said the process was up."""
    from fastapi.testclient import TestClient

    import iris_api

    monkeypatch.setattr(iris_api, "COMPANION_AVAILABLE", False)
    with pytest.raises(RuntimeError, match="refusing to start"):
        with TestClient(iris_api.app):
            pass


def test_the_documented_unit_can_write_the_data_directory():
    """ProtectHome=read-only with only logs/ writable: every import and every
    voice note failed under the unit the README documented."""
    unit = (Path(__file__).parent.parent / "scripts" / "iris.service.example").read_text()
    writable = next(line for line in unit.splitlines() if line.startswith("ReadWritePaths="))
    assert any(p.rstrip("/").endswith("/data") for p in writable.split("=", 1)[1].split())


# --- remembered analyses --------------------------------------------------------------

def test_decision_impact_is_computed_once_until_the_evidence_changes(test_user, monkeypatch):
    """Both surfaces asked every turn, over evidence that had not changed."""
    from agent.decision_impact import DecisionImpactEngine

    computed = []
    monkeypatch.setattr(DecisionImpactEngine, "_analyze_all_anchors",
                        lambda self: computed.append(1) or [])
    engine = DecisionImpactEngine(test_user["id"])

    engine.analyze_all_anchors()
    engine.analyze_all_anchors()
    assert len(computed) == 1, "the same evidence, the same hour: remembered"

    theme_id = db.create_theme(test_user["id"], [0.1] * 1536, "new",
                               datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat())
    db.add_theme_occurrence(theme_id, "reflection", 1, "x", 0.9, datetime.now(UTC).isoformat())
    engine.analyze_all_anchors()
    assert len(computed) == 2, "new evidence is computed, never served stale"

    engine.analyze_all_anchors(force_recompute=True)
    assert len(computed) == 3, "and the flag it always accepted now does something"


def test_tension_is_remembered_the_same_way(test_user, monkeypatch):
    from agent.tension import TensionEngine

    computed = []
    monkeypatch.setattr(TensionEngine, "_analyze_all_tensions",
                        lambda self: computed.append(1) or [])
    engine = TensionEngine(test_user["id"])
    engine.analyze_all_tensions()
    engine.analyze_all_tensions()
    assert len(computed) == 1


def test_a_theme_confidence_older_than_a_day_is_recomputed():
    """It was served for as long as a timestamp existed at all."""
    from agent.persistence import confidence_is_fresh

    now = datetime.now(UTC)
    assert confidence_is_fresh({"last_computed_at": now - timedelta(hours=1)})
    assert not confidence_is_fresh({"last_computed_at": now - timedelta(hours=25)})
    assert not confidence_is_fresh({"last_computed_at": None})
    assert not confidence_is_fresh(None)

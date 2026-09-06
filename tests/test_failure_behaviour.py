"""
How IRIS behaves when things go wrong.

Each of these pins a failure mode that used to be silent: a health check that
reported ok while the database was unreachable, an LLM outage that was written
into the conversation as Iris's own words, and a deleted entry that left its
evidence behind.
"""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

import iris_api
from agent.core import PersonalAICompanion
from agent.database import db
from agent.trackers.reflections import ReflectionService
from iris_api import app, get_current_user_id


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_is_ok_when_the_database_answers(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["checks"]["database"] == "ok"


def test_health_reports_503_when_the_database_is_unreachable(client, monkeypatch):
    """It used to return {"status": "ok"} unconditionally, so every data route
    could 500 while monitoring saw a green service."""
    def boom():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(iris_api.db, "ping", boom)
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["status"] == "degraded"
    assert r.json()["checks"]["database"] == "down"


def test_an_llm_outage_is_not_persisted_as_iris_speaking(test_user, monkeypatch):
    """Intelligence.chat used to *return* "Error calling API: ..." on failure,
    which core.chat then stored in conversation_messages as the assistant's
    reply — permanent history, re-fed as context on later turns."""
    monkeypatch.setattr("agent.pipeline.generate_embedding", lambda t, model=None: [0.3] * 1536)
    monkeypatch.setattr(
        "agent.persistence.PersistenceEngine._generate_theme_summary", lambda s, e: "T"
    )

    companion = PersonalAICompanion(user_id=test_user["id"])
    companion.intelligence.chat = MagicMock(side_effect=RuntimeError("provider is down"))

    with pytest.raises(RuntimeError):
        companion.chat("are you there?")

    history = db.get_chat_history(test_user["id"], limit=50)
    assert [m["content"] for m in history] == ["are you there?"], (
        "the user's message is kept, but no assistant turn should be invented"
    )
    assert not any("Error calling API" in m["content"] for m in history)


def test_deleting_a_reflection_removes_its_evidence(test_user, mock_pipeline_logic):
    """embeddings and theme_occurrences reference sources by (type, id) rather
    than by foreign key, so a deleted entry used to leave an embedding that
    still matched searches and an occurrence that still counted as evidence."""
    service = ReflectionService(test_user["id"])
    reflection_id = service.create_reflection(content="Work Stress today", energy_level=4)

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM embeddings WHERE source_type='reflection' AND source_id=%s;",
            (reflection_id,),
        )
        assert cur.fetchone()[0] == 1, "precondition: the entry was embedded"

    service.delete_reflection(reflection_id)

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM embeddings WHERE source_type='reflection' AND source_id=%s;",
            (reflection_id,),
        )
        assert cur.fetchone()[0] == 0, "the embedding must go with the entry"
        cur.execute(
            "SELECT count(*) FROM theme_occurrences WHERE source_type='reflection' AND source_id=%s;",
            (reflection_id,),
        )
        assert cur.fetchone()[0] == 0, "the occurrence must go with the entry"

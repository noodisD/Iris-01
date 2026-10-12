"""A chat added to IRIS as evidence, only at the owner's click (ADR-0032).

Every message below is invented. Nothing is sent: reading is offline in tests.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent import chat_evidence, pipeline, sessions
from agent.database import db
from iris_api import app, get_current_user_id


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def _chat(user_id: int, *turns: tuple[str, str]) -> str:
    session = db.create_chat_session(user_id)["id"]
    for role, text in turns:
        db.create_conversation_message(user_id, session, role, text)
    return session


def _stored(session_id: str) -> tuple[int | None, int | None]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT reflection_id, added_messages FROM chat_sessions WHERE id = %s", (session_id,))
        return cur.fetchone()


def test_an_added_chat_counts_only_the_owners_words(test_user):
    owner = test_user["id"]
    session = _chat(owner, ("user", "I skipped the pottery class again tonight."),
                    ("assistant", "What made tonight one to skip?"),
                    ("user", "I was dreading the teacher's comments on my bowl."))
    before = chat_evidence.status(owner, session)
    assert not before["added"] and before["yourMessages"] == 2 and before["dollars"] > 0
    assert "only context" in before["text"]

    done = chat_evidence.add(owner, session)
    assert done["added"] and done["newSinceAdded"] == 0
    reflection_id, counted = _stored(session)
    assert counted == 3
    entry = db.get_reflection(reflection_id)
    stored = sessions.read(entry["content"])
    assert stored.kind == "chat" and entry["content_format"] == "session"
    assert [t.role for t in stored.turns] == ["owner", "asker", "owner"]
    assert "conversation between the owner and IRIS" in sessions.describe(stored)
    assert sessions.owner_turn(entry["content"], "dreading the teacher's comments") is not None
    assert sessions.owner_turn(entry["content"], "What made tonight one to skip") is None
    assert reflection_id not in {r["id"] for r in db.get_latest_reflections(owner, 10)}
    assert reflection_id not in {r["id"] for r in db.get_journal_page(owner)}

    pipeline.run_processing_pipeline("reflection", reflection_id)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM session_passages WHERE reflection_id = %s", (reflection_id,))
        assert cur.fetchone()[0] == 0, "chat is recalled by message already"


def test_adding_again_after_it_went_on_replaces_the_old_copy(test_user):
    owner = test_user["id"]
    session = _chat(owner, ("user", "The bus was late so I walked."), ("assistant", "How was the walk?"))
    chat_evidence.add(owner, session)
    first, _ = _stored(session)
    assert chat_evidence.add(owner, session)["added"]
    assert _stored(session)[0] == first, "nothing new, nothing re-added"

    db.create_conversation_message(owner, session, "user", "Cold, but I liked it.")
    assert chat_evidence.status(owner, session)["newSinceAdded"] == 1
    chat_evidence.add(owner, session)
    second, counted = _stored(session)
    assert second != first and counted == 3
    assert db.get_reflection(first) is None


def test_a_chat_with_nothing_of_the_owners_cannot_be_added(client, test_user):
    session = _chat(test_user["id"], ("assistant", "How was today, really?"))
    refused = client.post(f"/api/conversations/{session}/evidence")
    assert refused.status_code == 409
    assert client.get("/api/conversations/missing/evidence").status_code == 404
    ok = _chat(test_user["id"], ("user", "A quiet day at the allotment."))
    assert client.get(f"/api/conversations/{ok}/evidence").json()["added"] is False
    assert client.post(f"/api/conversations/{ok}/evidence").json()["added"] is True

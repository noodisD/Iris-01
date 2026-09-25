"""
API contract tests for the chat / conversation slice.

These exercise the real FastAPI routes → real services → test DB, asserting the
wire shapes the frontend's `types/api.ts` expects (Conversation, ChatMessage, and
the SSE token stream). The single-user auth dependency is overridden to the
per-test `test_user` so we don't depend on the env default user.
"""

import json

import pytest
from fastapi.testclient import TestClient

from iris_api import app, get_current_user_id


@pytest.fixture
def client(test_user):
    """TestClient with the single-user auth dependency pinned to test_user."""
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def _open(client) -> str:
    opened = client.post("/api/conversations")
    assert opened.status_code == 200
    body = opened.json()
    assert body["messageCount"] == 0
    assert body["id"]
    return body["id"]


def test_opening_chat_starts_an_empty_session(client, test_user):
    """Each open is empty. Current is the latest open, not one rolling transcript."""
    first = _open(client)
    second = _open(client)
    assert first != second
    current = client.get("/api/conversations/current")
    assert current.status_code == 200
    data = current.json()
    assert data["id"] == second
    assert data["userId"] == str(test_user["id"])
    assert data["messageCount"] == 0
    assert "startedAt" in data and "lastMessageAt" in data


def test_messages_empty_for_new_user(client):
    """A fresh user has no history → empty ChatMessage[] (not an error)."""
    r = client.get("/api/conversations/conv_x/messages")
    assert r.status_code == 200
    assert r.json() == []


def test_stream_reply_emits_sse_tokens_then_done(client, mock_llm):
    """
    POST .../messages/stream streams `data: {"text": ...}` chunks whose
    concatenation is the reply, then a final `data: {"done": true, ...}`.
    mock_llm makes companion.chat() return the deterministic mock reply.
    """
    opened = _open(client)
    r = client.post(
        f"/api/conversations/{opened}/messages/stream",
        json={"text": "hello iris"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")

    body = r.text
    # Parse the SSE blocks back into events the way the frontend client does.
    events = []
    for block in body.split("\n\n"):
        data = "".join(
            line[len("data:"):].strip()
            for line in block.split("\n")
            if line.startswith("data:")
        )
        if data:
            events.append(json.loads(data))

    assert events, "expected at least one SSE event"
    assert events[-1].get("done") is True
    assert events[-1].get("messageId")
    reply = "".join(e.get("text", "") for e in events)
    assert "IRIS Mocked Response" in reply


def test_messages_reflect_history_after_chat(client, mock_llm):
    """After a streamed exchange, history exposes the user + iris messages."""
    opened = _open(client)
    client.post(
        f"/api/conversations/{opened}/messages/stream",
        json={"text": "remember this"},
    )
    r = client.get(f"/api/conversations/{opened}/messages")
    assert r.status_code == 200
    msgs = r.json()
    assert len(msgs) >= 2
    roles = {m["role"] for m in msgs}
    assert "user" in roles and "iris" in roles
    # ChatMessage shape
    sample = msgs[0]
    for key in ("id", "conversationId", "role", "text", "createdAt"):
        assert key in sample


def _events(body):
    events = []
    for block in body.split("\n\n"):
        data = "".join(line[len("data:"):].strip()
                       for line in block.split("\n") if line.startswith("data:"))
        if data:
            events.append(json.loads(data))
    return events


def test_the_reply_arrives_as_the_model_writes_it(client, mock_llm):
    """The route used to run the whole reply to completion and then drip it a
    word at a time — so the owner waited for the model and then again for an
    animation of a reply that already existed. Fragments pass through as the
    model produces them."""
    opened = _open(client)
    events = _events(client.post(f"/api/conversations/{opened}/messages/stream",
                                 json={"text": "hello"}).text)
    assert [e["text"] for e in events if "text" in e] == ["IRIS ", "Mocked ", "Response"]
    mock_llm.chat.assert_not_called()


def test_a_failed_reply_is_an_error_not_something_iris_said(client, mock_llm, test_user):
    """A failure used to arrive as a reply reading "I encountered an error…",
    in IRIS's voice. And half a streamed reply is not something IRIS said, so
    nothing is saved in its name — only the owner's own message."""
    def breaks(**kwargs):
        yield "Half a "
        raise RuntimeError("provider went away")
    mock_llm.stream.side_effect = breaks

    opened = _open(client)
    events = _events(client.post(f"/api/conversations/{opened}/messages/stream",
                                 json={"text": "are you there?"}).text)

    assert events[-1] == {"error": "provider went away", "saved": True}
    roles = [m["role"] for m in client.get(f"/api/conversations/{opened}/messages").json()]
    assert roles == ["user"], "the owner's message is kept; no partial reply is"


def test_a_message_that_could_not_be_stored_is_not_reported_as_saved(client, mock_llm, mocker):
    """`saved` answers one question: is what they typed in the database?

    It was sent as True for every failure, including a failure of the write
    that starts the turn — and the browser drops its draft on that word, so a
    failed save could take the only copy of the owner's writing with it.
    """
    mocker.patch("agent.database.db.create_conversation_message",
                 side_effect=RuntimeError("disk went away"))

    opened = _open(client)
    events = _events(client.post(f"/api/conversations/{opened}/messages/stream",
                                 json={"text": "please keep this"}).text)

    assert events[-1] == {"error": "disk went away", "saved": False}
    assert client.get(f"/api/conversations/{opened}/messages").json() == []


def test_a_new_open_does_not_show_stored_history(client, mock_llm, test_user):
    """Leaving and opening chat again is empty, but the earlier turn remains stored."""
    from agent.database import db
    first = _open(client)
    client.post(f"/api/conversations/{first}/messages/stream", json={"text": "remember this privately"})
    second = _open(client)
    assert client.get(f"/api/conversations/{second}/messages").json() == []
    assert any(m["content"] == "remember this privately" for m in db.get_chat_history(test_user["id"]))
    assert client.get(f"/api/conversations/{first}/messages").json()


def test_stream_refuses_an_unopened_conversation(client, mock_llm):
    refused = client.post("/api/conversations/conv_x/messages/stream", json={"text": "hello"})
    assert refused.status_code == 404
    mock_llm.stream.assert_not_called()


def test_a_new_session_reads_stored_history_without_showing_it(test_user):
    from agent.core import PersonalAICompanion
    from agent.database import db
    db.create_conversation_message(test_user["id"], "earlier", "user", "the lake was cold")
    session = db.create_chat_session(test_user["id"])
    companion = PersonalAICompanion(user_id=test_user["id"], session_id=session["id"])
    assert companion.memory.get_context() == []
    assert "the lake was cold" in companion._earlier_conversations()


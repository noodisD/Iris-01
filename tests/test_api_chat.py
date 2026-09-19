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


def test_current_conversation_shape(client, test_user):
    """GET /api/conversations/current returns the Conversation contract shape."""
    r = client.get("/api/conversations/current")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == f"conv_{test_user['id']}"
    assert data["userId"] == str(test_user["id"])
    assert isinstance(data["messageCount"], int)
    # Timestamps present and ISO-ish
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
    r = client.post(
        "/api/conversations/conv_x/messages/stream",
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
    client.post(
        "/api/conversations/conv_x/messages/stream",
        json={"text": "remember this"},
    )
    r = client.get("/api/conversations/conv_x/messages")
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
    events = _events(client.post("/api/conversations/conv_x/messages/stream",
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

    events = _events(client.post("/api/conversations/conv_x/messages/stream",
                                 json={"text": "are you there?"}).text)

    assert events[-1] == {"error": "provider went away", "saved": True}
    roles = [m["role"] for m in client.get("/api/conversations/conv_x/messages").json()]
    assert roles == ["user"], "the owner's message is kept; no partial reply is"

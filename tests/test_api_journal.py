"""
API contract tests for the journal slice (mapped onto reflections).

Asserts the frontend's JournalEntry / JournalListResponse shapes through the
real routes → ReflectionService → test DB. Single-user auth is overridden to
the test_user. mood (1-10) round-trips via the reflection's energy_level;
lines join/split on newlines into the reflection's content.
"""

import pytest
from fastapi.testclient import TestClient

from iris_api import app, get_current_user_id


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_create_journal_entry_returns_contract(client, test_user):
    r = client.post("/api/journal", json={"lines": ["line one", "line two"], "mood": 7})
    assert r.status_code == 200
    e = r.json()
    assert e["lines"] == ["line one", "line two"]
    assert e["mood"] == 7
    assert e["userId"] == str(test_user["id"])
    for key in ("id", "userId", "lines", "createdAt"):
        assert key in e, f"missing {key}"


def test_list_journal_returns_created_entry(client):
    client.post("/api/journal", json={"lines": ["hello world"], "mood": 5})
    r = client.get("/api/journal")
    assert r.status_code == 200
    data = r.json()
    assert "entries" in data
    assert any(e["lines"] == ["hello world"] for e in data["entries"])


def test_journal_mood_roundtrips(client):
    client.post("/api/journal", json={"lines": ["a single line"], "mood": 9})
    entries = client.get("/api/journal").json()["entries"]
    match = [e for e in entries if e["lines"] == ["a single line"]]
    assert match, "created entry not found in list"
    assert match[0]["mood"] == 9

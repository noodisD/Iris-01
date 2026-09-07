"""
API contract tests for the journal slice (mapped onto reflections).

Asserts the frontend's JournalEntry / JournalListResponse shapes through the
real routes → ReflectionService → test DB. Single-user auth is overridden to
the test_user. energy (1-10) round-trips via the reflection's energy_level;
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
    r = client.post("/api/journal", json={"lines": ["line one", "line two"], "energy": 7})
    assert r.status_code == 200
    e = r.json()
    assert e["lines"] == ["line one", "line two"]
    assert e["energy"] == 7
    assert e["userId"] == str(test_user["id"])
    for key in ("id", "userId", "lines", "createdAt"):
        assert key in e, f"missing {key}"


def test_list_journal_returns_created_entry(client):
    client.post("/api/journal", json={"lines": ["hello world"], "energy": 5})
    r = client.get("/api/journal")
    assert r.status_code == 200
    data = r.json()
    assert "entries" in data
    assert any(e["lines"] == ["hello world"] for e in data["entries"])


def test_journal_energy_roundtrips(client):
    client.post("/api/journal", json={"lines": ["a single line"], "energy": 9})
    entries = client.get("/api/journal").json()["entries"]
    match = [e for e in entries if e["lines"] == ["a single line"]]
    assert match, "created entry not found in list"
    assert match[0]["energy"] == 9


def test_journal_pagination_uses_the_cursor(client):
    """The frontend has always sent ?cursor=; the backend used to ignore it and
    return page one forever, while the contract advertised nextCursor."""
    for i in range(5):
        client.post("/api/journal", json={"lines": [f"entry {i}"], "energy": 5})

    first = client.get("/api/journal?limit=2").json()
    assert len(first["entries"]) == 2
    assert "nextCursor" in first, "more entries exist, so a cursor must be offered"

    second = client.get(f"/api/journal?limit=2&cursor={first['nextCursor']}").json()
    assert len(second["entries"]) == 2

    first_ids = {e["id"] for e in first["entries"]}
    second_ids = {e["id"] for e in second["entries"]}
    assert not (first_ids & second_ids), "pages must not overlap"


def test_journal_last_page_offers_no_cursor(client):
    client.post("/api/journal", json={"lines": ["only one"], "energy": 5})
    page = client.get("/api/journal?limit=50").json()
    assert "nextCursor" not in page


def test_journal_rejects_a_bad_cursor(client):
    assert client.get("/api/journal?cursor=not-a-number").status_code == 400

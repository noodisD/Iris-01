"""
API contract tests for the settings slice.

Asserts the frontend's User / UserPreferences / KnownFact / DataConnector shapes
through the real routes. Single-user auth is overridden to the test_user.
- preferences live in the new user_app_settings store (separate from engine prefs)
- KnownFact[] is mapped from the user's themes
- connectors are a static list whose state persists in user_app_settings
"""

import pytest
from fastapi.testclient import TestClient

from iris_api import app, get_current_user_id


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_get_user_returns_contract(client, test_user):
    r = client.get("/api/user")
    assert r.status_code == 200
    u = r.json()
    for key in ("id", "name", "createdAt", "dayInJourney", "timezone", "preferences"):
        assert key in u, f"missing {key}"
    assert u["id"] == str(test_user["id"])
    prefs = u["preferences"]
    for key in ("tone", "density", "maxNudgesPerDay", "threadsListenedFor"):
        assert key in prefs, f"missing preference {key}"
    assert isinstance(prefs["threadsListenedFor"], list)


def test_update_preferences_roundtrips(client):
    r = client.patch("/api/user/preferences", json={"tone": "clinical", "density": "dense"})
    assert r.status_code == 200
    prefs = r.json()["preferences"]
    assert prefs["tone"] == "clinical"
    assert prefs["density"] == "dense"
    # persists across a fresh GET
    again = client.get("/api/user").json()["preferences"]
    assert again["tone"] == "clinical"


def test_update_preferences_threads(client):
    r = client.patch("/api/user/preferences", json={"threadsListenedFor": ["mood", "sleep"]})
    assert r.status_code == 200
    assert r.json()["preferences"]["threadsListenedFor"] == ["mood", "sleep"]


def test_knowledge_lists_themes_as_facts(client, test_user):
    from agent.database import db
    db.create_theme(test_user["id"], [0.0] * 1536, "Prefers mornings for deep work",
                    "2026-01-01T00:00:00", "2026-06-01T00:00:00", 4)
    r = client.get("/api/knowledge")
    assert r.status_code == 200
    facts = r.json()
    assert isinstance(facts, list)
    match = [f for f in facts if f["fact"] == "Prefers mornings for deep work"]
    assert match, "created theme not surfaced as a KnownFact"
    f = match[0]
    for key in ("id", "fact", "source", "ageDays", "editable"):
        assert key in f, f"missing {key}"
    assert f["ageDays"] >= 0


def test_forget_fact_deletes_theme(client, test_user):
    from agent.database import db
    tid = db.create_theme(test_user["id"], [0.0] * 1536, "Drinks too much coffee",
                          "2026-01-01T00:00:00", "2026-06-01T00:00:00", 1)
    r = client.delete(f"/api/knowledge/{tid}")
    assert r.status_code in (200, 204)
    remaining = [f["id"] for f in client.get("/api/knowledge").json()]
    assert str(tid) not in remaining


def test_get_connectors_returns_contract(client):
    r = client.get("/api/connectors")
    assert r.status_code == 200
    connectors = r.json()
    assert isinstance(connectors, list) and connectors
    c = connectors[0]
    for key in ("id", "name", "scopeDescription", "state"):
        assert key in c, f"missing {key}"
    assert c["state"] in ("connected", "paused", "off")


def test_connector_state_persists(client):
    r = client.post("/api/connectors/calendar/connect")
    assert r.status_code == 200
    assert r.json()["state"] == "connected"
    # persists across a fresh GET
    connectors = {c["id"]: c for c in client.get("/api/connectors").json()}
    assert connectors["calendar"]["state"] == "connected"

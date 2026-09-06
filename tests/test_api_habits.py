"""
API contract tests for the habits slice.

Asserts the wire shapes the frontend's `types/api.ts` expects (Habit and
HabitsTodayResponse) and the toggle behavior, through the real routes →
HabitTracker → test DB. Single-user auth is overridden to the test_user.
"""

import pytest
from fastapi.testclient import TestClient

from iris_api import app, get_current_user_id


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_create_habit_returns_contract_shape(client, test_user):
    r = client.post(
        "/api/habits",
        json={"name": "Meditate", "tag": "10 min · morning", "intent": "calm down", "color": "sage"},
    )
    assert r.status_code == 200
    h = r.json()
    assert h["name"] == "Meditate"
    assert h["userId"] == str(test_user["id"])
    assert h["color"] == "sage"
    for key in ("id", "name", "tag", "color", "supports", "streakDays", "bestStreak", "doneToday", "recentDays"):
        assert key in h, f"missing {key}"
    assert isinstance(h["recentDays"], list) and all(v in (0, 1) for v in h["recentDays"])
    assert h["doneToday"] is False


def test_today_lists_created_habit_with_aggregates(client):
    client.post("/api/habits", json={"name": "Walk", "tag": "daily", "intent": "move", "color": "amber"})
    r = client.get("/api/habits/today")
    assert r.status_code == 200
    data = r.json()
    for key in ("habits", "doneCount", "totalCount", "consistency30d", "longestActiveStreak"):
        assert key in data, f"missing {key}"
    assert data["totalCount"] == len(data["habits"])
    assert "Walk" in [h["name"] for h in data["habits"]]
    assert 0.0 <= data["consistency30d"] <= 1.0


def test_toggle_marks_done_then_reverts(client):
    created = client.post(
        "/api/habits",
        json={"name": "Read", "tag": "daily", "intent": "learn", "color": "indigo"},
    ).json()
    hid = created["id"]

    on = client.post(f"/api/habits/{hid}/toggle", json={"done": True})
    assert on.status_code == 200
    assert on.json()["doneToday"] is True
    assert on.json()["streakDays"] >= 1

    today = client.get("/api/habits/today").json()
    assert today["doneCount"] >= 1

    off = client.post(f"/api/habits/{hid}/toggle", json={"done": False})
    assert off.status_code == 200
    assert off.json()["doneToday"] is False


def test_toggle_unknown_habit_is_404(client):
    r = client.post("/api/habits/99999999/toggle", json={"done": True})
    assert r.status_code == 404

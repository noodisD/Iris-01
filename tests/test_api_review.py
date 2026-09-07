"""
API contract tests for the review slice.

Seeds reflections (energy) + a habit completion in the current week, then asserts
the frontend's ReviewWeek shape. The longform letter is LLM-generated, so tests
run under mock_llm (the letter is asserted as a non-empty string, not by content)
to stay deterministic and cost-free. Single-user auth overridden to test_user.
"""

import pytest
from fastapi.testclient import TestClient

from agent.trackers.habits import HabitTracker
from agent.trackers.reflections import ReflectionService
from iris_api import app, get_current_user_id


@pytest.fixture
def client(test_user, mock_llm):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_week(test_user):
    svc = ReflectionService(test_user["id"])
    svc.create_reflection(content="Good momentum today", energy_level=8, tags=["win"])
    svc.create_reflection(content="A bit drained", energy_level=4, tags=[])
    tracker = HabitTracker(test_user["id"])
    hid = tracker.create_habit(name="Morning walk", category="health")
    tracker.log_completion(hid)
    return test_user["id"]


def test_review_latest_returns_contract(client, seeded_week):
    r = client.get("/api/review/latest")
    assert r.status_code == 200
    week = r.json()
    for key in ("weekStart", "weekEnd", "letter", "metrics", "days", "themes", "lookahead"):
        assert key in week, f"missing {key}"
    assert isinstance(week["letter"], str) and week["letter"]
    for key in ("energyAvg", "energyDelta",
                "habitsHit", "habitsTotal", "winsLogged"):
        assert key in week["metrics"], f"missing metric {key}"


def test_review_days_and_themes_shape(client, seeded_week):
    week = client.get("/api/review/latest").json()
    assert len(week["days"]) == 7
    for d in week["days"]:
        for key in ("date", "shortName", "energy", "word"):
            assert key in d, f"missing day field {key}"
    assert isinstance(week["themes"], list)
    assert len(week["themes"]) <= 3


def test_review_habits_reflect_completion(client, seeded_week):
    metrics = client.get("/api/review/latest").json()["metrics"]
    assert metrics["habitsTotal"] >= 1
    assert metrics["habitsHit"] >= 1


def test_review_specific_week(client, seeded_week):
    from datetime import date, timedelta
    start = (date.today() - timedelta(days=6)).isoformat()
    r = client.get(f"/api/review/week/{start}")
    assert r.status_code == 200
    assert r.json()["weekStart"] == start

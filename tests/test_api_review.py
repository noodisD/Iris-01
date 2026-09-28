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
    for key in ("energyAvg", "energyDelta", "habitsHit", "habitsTotal"):
        assert key in week["metrics"], f"missing metric {key}"


def test_the_week_is_not_scored(client, seeded_week):
    """"Wins" were entries with energy of 7 or more, and each day got a word
    bucketed from its energy — IRIS scoring the owner's week. A day now shows
    what the owner reported, or that nothing was written."""
    week = client.get("/api/review/latest").json()
    assert "winsLogged" not in week["metrics"] and "winThatMattered" not in week
    words = {d["word"] for d in week["days"]}
    assert not words & {"bright", "steady", "mixed", "heavy", "quiet"}
    assert "8/10" in words or "4/10" in words, "the owner's own number, as reported"


def test_a_week_with_no_energy_reported_has_no_average(client, test_user):
    """0.0 stood in for "nothing reported": the lowest week possible, and the
    next week a large rise against it."""
    ReflectionService(test_user["id"]).create_reflection(content="Just a note.")
    metrics = client.get("/api/review/latest").json()["metrics"]
    assert metrics["energyAvg"] is None and metrics["energyDelta"] is None


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




def test_the_letter_is_written_once_and_kept_until_the_week_changes(client, seeded_week, mock_llm, monkeypatch):
    """Each view used to recompute every finding and ask the model again."""
    admitted = []
    real_admit = __import__("agent.pipeline_orchestrator", fromlist=["admit"]).admit
    monkeypatch.setattr("agent.pipeline_orchestrator.admit", lambda user_id: admitted.append(user_id) or real_admit(user_id))

    first = client.get("/api/review/latest").json()["letter"]
    calls = mock_llm.chat.call_count
    assert client.get("/api/review/latest").json()["letter"] == first
    assert mock_llm.chat.call_count == calls, "a second view must not ask the model again"
    assert len(admitted) == 1, "a second view must not recompute the findings"

    ReflectionService(seeded_week).create_reflection(content="Another evening walk", energy_level=6)
    client.get("/api/review/latest")
    assert mock_llm.chat.call_count == calls + 1, "a new entry is a new letter"


def test_a_failed_letter_is_not_kept(client, seeded_week, mock_llm):
    mock_llm.chat.side_effect = RuntimeError("provider down")
    client.get("/api/review/latest")
    mock_llm.chat.side_effect = None
    calls = mock_llm.chat.call_count
    client.get("/api/review/latest")
    assert mock_llm.chat.call_count == calls + 1, "after a failure the next view tries again"

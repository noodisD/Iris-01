"""The analytical gates, reachable from the app rather than only the CLI.

CONTEXT.md says "User preferences override all gates", and in the engines they
always have — the confidence threshold, the item budget and engine enablement
are read from user_preferences on every analysis. What was missing was any way
to set them outside the CLI, so the documented control existed for a user with
a terminal and not for the one using the app.

The tests that matter here are not the round-trips. They are the two that check
a setting changes what IRIS will actually say, because a control that stores a
value and changes nothing is worse than no control at all.
"""

import pytest
from fastapi.testclient import TestClient

from iris_api import app, get_current_user_id
from agent.insights_service import InsightsService
from agent.preferences import UserPreferencesService


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def _raw(engine, key, confidence, theme_id=1):
    return {
        "engine": engine, "pattern_key": key, "theme_id": theme_id,
        "summary": f"{key} theme", "label": "persisting",
        "recent": 3, "past": 5, "confidence_level": confidence,
    }


def test_defaults_are_returned_before_anything_is_set(client, test_user):
    body = client.get("/api/user/analysis").json()
    assert body["minConfidence"] == "medium"
    assert body["maxItems"] == 5
    assert body["enabledEngines"] is None, "null means every engine"
    assert "persistence" in body["availableEngines"], (
        "the UI takes the engine list from the server rather than keeping its own"
    )


def test_each_gate_round_trips(client, test_user):
    r = client.patch("/api/user/analysis", json={"minConfidence": "high", "maxItems": 2})
    assert r.status_code == 200, r.text
    assert r.json()["minConfidence"] == "high"
    assert r.json()["maxItems"] == 2

    assert client.get("/api/user/analysis").json()["maxItems"] == 2, "must persist"


def test_raising_the_threshold_changes_what_iris_will_say(client, test_user, monkeypatch):
    """The point of the whole feature: the control reaches the gate."""
    def _service():
        s = InsightsService(test_user["id"])
        monkeypatch.setattr(s, "_normalize", lambda: [_raw("trajectory", "b", "medium", 2)])
        return s

    client.patch("/api/user/analysis", json={"minConfidence": "medium"})
    assert {i["id"] for i in _service().list_summaries()} == {"trajectory:b"}

    client.patch("/api/user/analysis", json={"minConfidence": "high"})
    assert _service().list_summaries() == [], (
        "raising the threshold from the app must suppress a medium finding"
    )


def test_disabling_an_engine_silences_it(client, test_user, monkeypatch):
    def _service():
        s = InsightsService(test_user["id"])
        monkeypatch.setattr(
            s, "_normalize",
            lambda: [_raw("resolution", "a", "high", 1), _raw("trajectory", "b", "high", 2)],
        )
        return s

    assert {i["id"] for i in _service().list_summaries()} == {"resolution:a", "trajectory:b"}

    client.patch("/api/user/analysis", json={"enabledEngines": ["resolution"]})
    assert {i["id"] for i in _service().list_summaries()} == {"resolution:a"}, (
        "an engine switched off in the app must stop contributing"
    )


@pytest.mark.parametrize("payload,reason", [
    ({"minConfidence": "extremely"}, "not one of low/medium/high"),
    ({"maxItems": 0}, "below the range"),
    ({"maxItems": 99}, "above the range"),
    ({"enabledEngines": ["astrology"]}, "not an engine"),
    ({"enabledEngines": "resolution"}, "not a list"),
])
def test_invalid_values_are_rejected_not_ignored(client, test_user, payload, reason):
    """A control that appears to work and silently does nothing is the failure
    mode this feature exists to remove, so bad input is a 400."""
    before = client.get("/api/user/analysis").json()
    r = client.patch("/api/user/analysis", json=payload)
    assert r.status_code == 400, f"{reason}: expected 400, got {r.status_code}"
    assert client.get("/api/user/analysis").json() == before, "a rejected write must not change anything"


def test_an_unknown_setting_is_rejected(client, test_user):
    r = client.patch("/api/user/analysis", json={"tone": "warm"})
    assert r.status_code == 400
    assert "tone" in r.json()["detail"], "say which key was not understood"


def test_reset_restores_the_defaults(client, test_user):
    client.patch("/api/user/analysis", json={"minConfidence": "high", "maxItems": 1})
    body = client.post("/api/user/analysis/reset").json()
    assert body["minConfidence"] == "medium"
    assert body["maxItems"] == 5
    assert body["enabledEngines"] is None


def test_the_cli_and_the_app_share_one_store(client, test_user):
    """Both surfaces write the same preferences, so a value set in one is the
    value the other sees."""
    UserPreferencesService(test_user["id"]).update_pref("min_confidence", "high")
    assert client.get("/api/user/analysis").json()["minConfidence"] == "high"

    client.patch("/api/user/analysis", json={"minConfidence": "low"})
    assert UserPreferencesService(test_user["id"]).get_prefs()["min_confidence"] == "low"

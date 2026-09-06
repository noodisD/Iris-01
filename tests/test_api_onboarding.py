"""
API contract tests for the onboarding slice.

Asserts the frontend's OnboardingState shape. Answers persist into the
user_app_settings store; completing onboarding flips the step to 'done' and
returns the `User` contract. Single-user auth overridden to test_user.
"""

import pytest
from fastapi.testclient import TestClient

from iris_api import app, get_current_user_id


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_initial_state_has_empty_answers(client):
    r = client.get("/api/onboarding/state")
    assert r.status_code == 200
    state = r.json()
    assert "step" in state and "answers" in state
    assert state["answers"] == {}
    assert state["step"] != "done"


def test_answers_merge_and_persist(client):
    client.post("/api/onboarding/answer", json={"step": "name", "answer": {"name": "Sam"}})
    r = client.post("/api/onboarding/answer", json={"step": "threads", "answer": {"threads": ["mood", "sleep"]}})
    assert r.status_code == 200
    state = r.json()
    assert state["answers"]["name"] == "Sam"
    assert state["answers"]["threads"] == ["mood", "sleep"]
    # persists across a fresh GET
    again = client.get("/api/onboarding/state").json()
    assert again["answers"]["name"] == "Sam"
    assert again["step"] != "done"  # still missing reason/bodySource/checkin


def test_complete_marks_done_and_returns_user(client, test_user):
    client.post("/api/onboarding/answer", json={"step": "name", "answer": {"name": "Sam"}})
    r = client.post("/api/onboarding/complete")
    assert r.status_code == 200
    user = r.json()
    assert user["id"] == str(test_user["id"])
    assert "preferences" in user
    # name answered during onboarding is reflected on the user
    assert user["name"] == "Sam"
    assert client.get("/api/onboarding/state").json()["step"] == "done"

"""
API contract tests for the onboarding slice.

Asserts the frontend's OnboardingState shape: 'welcome' until the one
button is pressed, then 'done', returning the `User` contract. Single-user auth overridden to test_user.
"""

import pytest
from fastapi.testclient import TestClient

from iris_api import app, get_current_user_id


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_first_run_is_one_step(client):
    """The five-step machine (name, reason, threads, body source, review) was
    walked by no screen; first run is one paragraph and one button."""
    assert client.get("/api/onboarding/state").json() == {"step": "welcome"}


def test_complete_marks_done_and_returns_user(client, test_user):
    r = client.post("/api/onboarding/complete")
    assert r.status_code == 200
    user = r.json()
    assert user["id"] == str(test_user["id"])
    assert "preferences" in user
    assert client.get("/api/onboarding/state").json() == {"step": "done"}


def test_the_answer_route_is_gone(client):
    assert client.post("/api/onboarding/answer",
                       json={"step": "name", "answer": {"name": "x"}}).status_code in (404, 405)

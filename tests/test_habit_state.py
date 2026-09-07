"""
Habit bookkeeping must not report a skip as a success.

habit_completions.is_completed defaults to TRUE, and the skip insert never set
it — only the ON CONFLICT branch did. So the *first* skip on a given date was
stored as completed and skipped at once, and everything counting completions
counted it.

Separately, today's consistency divided by 30 days no matter how old the habit
was, so a habit created and kept today read as 3% rather than 100% — while the
consistency report endpoint divides by the habit's age and answers 100%. Two
endpoints, one question, two answers.
"""

import pytest
from fastapi.testclient import TestClient

from agent.database import db
from agent.trackers.habits import HabitTracker
from iris_api import app, get_current_user_id


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_a_first_skip_is_not_recorded_as_a_completion(test_user):
    tracker = HabitTracker(test_user["id"])
    habit_id = tracker.create_habit(name="Yoga", category="health")

    tracker.log_skip(habit_id, reason="too tired")

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT is_completed, is_skipped FROM habit_completions WHERE habit_id = %s;",
            (habit_id,),
        )
        is_completed, is_skipped = cur.fetchone()
    assert is_skipped is True
    assert is_completed is False, "a skip is not a completion"


def test_a_skipped_day_does_not_count_as_done_today(client, test_user):
    tracker = HabitTracker(test_user["id"])
    habit_id = tracker.create_habit(name="Walk", category="health")
    tracker.log_skip(habit_id)

    today = client.get("/api/habits/today").json()
    assert today["doneCount"] == 0, "a skipped habit must not be counted as done"
    assert today["habits"][0]["doneToday"] is False


def test_a_brand_new_habit_kept_today_is_fully_consistent(client, test_user):
    """The denominator is the habit's life so far, not a flat 30 days."""
    created = client.post(
        "/api/habits", json={"name": "Meditate", "tag": "daily", "intent": "calm", "color": "sage"}
    ).json()
    client.post(f"/api/habits/{created['id']}/toggle", json={"done": True})

    today = client.get("/api/habits/today").json()
    assert today["consistency30d"] == pytest.approx(1.0), (
        f"a habit created and kept today is 100% consistent, got {today['consistency30d']}"
    )


def test_consistency_agrees_between_the_two_endpoints(client, test_user):
    """/habits/today and /habits/consistency answered the same question
    differently: one divided by 30, the other by the habit's age."""
    created = client.post(
        "/api/habits", json={"name": "Read", "tag": "daily", "intent": "learn", "color": "indigo"}
    ).json()
    client.post(f"/api/habits/{created['id']}/toggle", json={"done": True})

    today = client.get("/api/habits/today").json()["consistency30d"]
    report = client.get("/api/habits/consistency/30").json()
    # The report formats its rate as a string like "100.0%".
    reported = float(report["habits"][0]["completion_rate"].rstrip("%")) / 100.0

    assert today == pytest.approx(reported, abs=0.01), (
        f"the two endpoints disagree: today={today}, report={reported}"
    )

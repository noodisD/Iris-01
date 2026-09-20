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

from datetime import date, datetime, timedelta

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


def test_changing_a_completion_to_a_skip_takes_back_its_evidence(test_user, monkeypatch):
    """The owner says it did not happen. Until now only the completion row
    heard: its embedding, its theme occurrences and its queued job stayed, so
    something they had taken back went on being counted."""
    monkeypatch.setattr("agent.pipeline.generate_embedding", lambda text, model=None: [0.3] * 1536)
    user_id = test_user["id"]
    tracker = HabitTracker(user_id)
    habit_id = tracker.create_habit(name="Evening walk", description="unwind", category="health")
    today = date.today()
    completion_id = db.log_habit_completion(habit_id, today, notes="walked the long way")

    theme_id = db.create_theme(user_id, [0.3] * 1536, "Walking",
                               (datetime.now() - timedelta(days=30)).isoformat(),
                               datetime.now().isoformat())
    db.add_theme_occurrence(theme_id, "habit_completion", completion_id, "walked", 0.9,
                            datetime.now().isoformat())
    db.add_embedding("habit_completion", completion_id, "test_model", [0.3] * 1536)

    db.log_habit_skip(habit_id, today, reason="too tired")

    with db.connection() as conn, conn.cursor() as cur:
        for table in ("theme_occurrences", "embeddings", "processing_queue"):
            cur.execute(f"SELECT count(*) FROM {table} WHERE source_type = 'habit_completion' "
                        "AND source_id = %s;", (completion_id,))
            assert cur.fetchone()[0] == 0, f"{table} still holds the retracted day"
    assert db.get_theme_by_id(theme_id)["occurrence_count"] == 0, (
        "the theme's stored count is what the readers use")

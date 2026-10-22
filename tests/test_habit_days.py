"""Habits: any past day can be fixed, each day can carry a note, and habits can be
weekly or monthly. Every habit and note below is invented."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from agent.database import db
from agent.trackers.streaks import compute
from iris_api import app, get_current_user_id

TODAY = date.today()


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def _habit(client, **extra) -> dict:
    created = client.post("/api/habits", json={"name": "Water the allotment", **extra})
    assert created.status_code == 200
    return created.json()


def _set(client, hid, day: date, status: str, note: str | None = None):
    return client.put(f"/api/habits/{hid}/days/{day.isoformat()}", json={"status": status, "note": note})


# --- streak rules --------------------------------------------------------------------

def test_streaks_are_counted_from_the_days():
    d = lambda *n: {TODAY - timedelta(days=k) for k in n}
    assert compute("daily", 1, d(0, 1, 2), set(), TODAY).current == 3
    assert compute("daily", 1, d(1, 2), set(), TODAY).current == 2, "today still in progress"
    assert compute("daily", 1, d(0, 2, 3), d(1), TODAY).current == 3, "a skipped day pauses the streak"
    gap = compute("daily", 1, d(0, 2, 3, 4), set(), TODAY)
    assert (gap.current, gap.longest) == (1, 3)
    monday = TODAY - timedelta(days=TODAY.weekday())
    weeks = {monday - timedelta(days=7), monday - timedelta(days=6), monday - timedelta(days=14),
             monday - timedelta(days=13)}
    assert compute("weekly", 2, weeks, set(), TODAY).current == 2
    assert compute("weekly", 2, weeks | {monday}, set(), TODAY).period_done == 1


# --- fixing a forgotten day ------------------------------------------------------------

def test_a_forgotten_day_can_be_marked_and_the_streak_follows(client):
    h = _habit(client)
    for k in (0, 1, 2):
        assert _set(client, h["id"], TODAY - timedelta(days=k), "done").status_code == 200
    assert client.get("/api/habits").json()[0]["streakDays"] == 3
    fixed = _set(client, h["id"], TODAY - timedelta(days=3), "done").json()["habit"]
    assert fixed["streakDays"] == 4 and fixed["bestStreak"] == 4
    assert _set(client, h["id"], TODAY + timedelta(days=1), "done").status_code == 400, "not the future"


def test_a_note_belongs_to_the_day_and_survives_unticking(client):
    h = _habit(client)
    yesterday = TODAY - timedelta(days=1)
    _set(client, h["id"], yesterday, "done", "Watered before the rain came in.")
    client.post(f"/api/habits/{h['id']}/toggle", json={"done": False, "date": yesterday.isoformat()})
    days = client.get(f"/api/habits/{h['id']}/days").json()
    assert days == [{"date": yesterday.isoformat(), "status": "none", "note": "Watered before the rain came in."}]
    client.post(f"/api/habits/{h['id']}/toggle", json={"done": True, "date": yesterday.isoformat()})
    assert client.get(f"/api/habits/{h['id']}/days").json()[0] == {
        "date": yesterday.isoformat(), "status": "done", "note": "Watered before the rain came in."}
    _set(client, h["id"], yesterday, "none", "")
    assert client.get(f"/api/habits/{h['id']}/days").json() == [], "nothing left: the day is gone"


def test_only_a_done_day_is_evidence_and_each_is_recalled_as_what_it_was(client):
    h = _habit(client)
    hid = int(h["id"])
    _set(client, hid, TODAY, "done", "Slow but steady.")
    _set(client, hid, TODAY - timedelta(days=1), "skipped", "Too windy to stand outside.")
    _set(client, hid, TODAY - timedelta(days=2), "none", "Thought about it all evening.")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, completion_date FROM habit_completions WHERE habit_id = %s", (hid,))
        ids = {day: cid for cid, day in cur.fetchall()}
    assert db.is_evidence_eligible("habit_completion", ids[TODAY])
    assert not db.is_evidence_eligible("habit_completion", ids[TODAY - timedelta(days=1)])
    assert not db.is_evidence_eligible("habit_completion", ids[TODAY - timedelta(days=2)])
    said = [db.get_memory_item("habit_completion", ids[TODAY - timedelta(days=k)])["text"] for k in (0, 1, 2)]
    assert said == ["Did Water the allotment: Slow but steady.",
                    "Skipped Water the allotment: Too windy to stand outside.",
                    "Note on Water the allotment: Thought about it all evening."]


# --- editing habits, and periods ------------------------------------------------------------

def test_a_habit_can_be_edited_archived_and_deleted(client):
    h = _habit(client, intent="So the beans survive")
    edited = client.patch(f"/api/habits/{h['id']}", json={"name": "Water the beans", "tag": "garden",
                                                           "frequency": "weekly", "target": 3}).json()
    assert (edited["name"], edited["tag"], edited["frequency"], edited["target"], edited["streakUnit"]) == \
        ("Water the beans", "garden", "weekly", 3, "week")
    archived = client.patch(f"/api/habits/{h['id']}", json={"archived": True}).json()
    assert archived["archived"] is True
    assert h["id"] not in [x["id"] for x in client.get("/api/habits/today").json()["habits"]]
    assert h["id"] in [x["id"] for x in client.get("/api/habits").json()]
    _set(client, h["id"], TODAY, "done", "A note to be deleted.")
    assert client.delete(f"/api/habits/{h['id']}").json() == {"deleted": True}
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM habit_completions WHERE habit_id = %s", (int(h["id"]),))
        assert cur.fetchone()[0] == 0
    assert client.get(f"/api/habits/{h['id']}/days").status_code == 404


def test_a_weekly_habit_reports_progress_this_week(client):
    h = _habit(client, frequency="weekly", target=2)
    monday = TODAY - timedelta(days=TODAY.weekday())
    _set(client, h["id"], monday, "done")
    weekly = next(x for x in client.get("/api/habits").json() if x["id"] == h["id"])
    assert (weekly["periodDone"], weekly["periodMet"], weekly["target"]) == (1, False, 2)
    assert weekly["periods"][-1] == {"start": monday.isoformat(), "done": 1, "met": False}
    monthly = _habit(client, frequency="monthly", target=1)
    assert monthly["frequency"] == "monthly" and monthly["streakUnit"] == "month"

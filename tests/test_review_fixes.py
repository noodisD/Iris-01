"""The bugs from the whole-codebase review of 25 September, each pinned by the
scenario that showed it.

Fixtures are invented and neutral: no archive text.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import iris_api
from agent.database import db
from agent.importing import store
from iris_api import _age_days, app, get_current_user_id

ENTRY = "A long walk by the river, then an early night with a book about gardens."


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def _upload(client, days: list[str]) -> dict:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for d in days:
            zf.writestr(f"{d}.md", f"{ENTRY} Written on {d}.")
    r = client.post("/api/import/batches", files={"file": ("export.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 200, r.text
    return r.json()


# --- import ---------------------------------------------------------------

def test_a_partly_committed_import_cannot_be_read_again(client, test_user):
    """Re-reading replaced every item row, including the ones that link the
    batch to the entries it created, so undo could no longer find them."""
    batch = _upload(client, ["2024-05-01", "2024-05-02"])
    assert client.post(f"/api/import/batches/{batch['id']}/commit").status_code == 200
    # As a commit where one entry failed leaves it.
    store.update_batch(batch["id"], status="failed")

    r = client.post(f"/api/import/batches/{batch['id']}/reparse", json={"adapter": "dated_files"})

    assert r.status_code == 400
    assert "already in your journal" in r.json()["detail"]
    assert len(store.reflection_ids_for_batch(batch["id"], test_user["id"])) == 2, \
        "the links undo depends on are still there"


def test_a_commit_already_running_is_not_run_twice(client, test_user):
    """Two commits racing listed the same items, and the loser relabelled the
    winner's imports as duplicates."""
    batch = _upload(client, ["2024-05-03"])
    assert store.claim_batch(batch["id"], test_user["id"], ("needs_review", "failed"), "committing")

    r = client.post(f"/api/import/batches/{batch['id']}/commit")

    assert r.status_code == 409
    assert "already being committed" in r.json()["detail"]
    assert store.counts(batch["id"]).get("duplicate", 0) == 0


def test_a_commit_left_by_a_dead_process_can_be_taken_over(test_user):
    batch_id = store.create_batch(test_user["id"], "text", "export.zip", None)
    store.update_batch(batch_id, status="committing")
    assert not store.claim_batch(batch_id, test_user["id"], ("needs_review",), "committing")

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE import_batches SET updated_at = NOW() - interval '1 hour' WHERE id = %s;",
                    (batch_id,))
        conn.commit()

    assert store.claim_batch(batch_id, test_user["id"], ("needs_review",), "committing")


# --- journal paging -------------------------------------------------------

def test_paging_reaches_an_app_entry_written_after_imported_ones_on_the_same_day(client, test_user):
    """Imported entries carry a sequence and app entries do not, so within a day
    the sort is not id order. A cursor of (date, id) skipped the app entry."""
    day = date(2024, 6, 1)
    first = db.create_reflection(test_user["id"], "Imported, first in its file.", reflection_date=day,
                                 source="import", entry_sequence=1)
    second = db.create_reflection(test_user["id"], "Imported, second in its file.", reflection_date=day,
                                  source="import", entry_sequence=2)
    written = db.create_reflection(test_user["id"], "Written in the app that evening.", reflection_date=day)

    seen, cursor = [], None
    for _ in range(10):
        r = client.get("/api/journal", params={"limit": 1, **({"cursor": cursor} if cursor else {})})
        assert r.status_code == 200
        body = r.json()
        seen += [int(e["id"]) for e in body["entries"]]
        cursor = body.get("nextCursor")
        if not cursor:
            break

    assert seen == [second, first, written]


# --- habits ---------------------------------------------------------------

def test_undoing_a_habits_only_tick_clears_its_streak(client):
    created = client.post("/api/habits", json={"name": "Stretch", "tag": "daily"}).json()
    client.post(f"/api/habits/{created['id']}/toggle", json={"done": True})
    client.post(f"/api/habits/{created['id']}/toggle", json={"done": False})

    habit = next(h for h in client.get("/api/habits/today").json()["habits"] if h["id"] == created["id"])

    assert habit["streakDays"] == 0
    assert habit["bestStreak"] == 0


# --- validation -----------------------------------------------------------

@pytest.mark.parametrize("days", [-1, 0, 10**9])
def test_a_snooze_length_out_of_range_is_refused(client, days):
    r = client.post("/api/insights/anything/snooze", json={"days": days})
    assert r.status_code == 422


def test_a_bad_preference_value_is_refused_not_reported_as_saved(client):
    r = client.patch("/api/user/preferences", json={"maxNudgesPerDay": "x"})
    assert r.status_code == 422


def test_a_valid_preference_is_saved(client):
    r = client.patch("/api/user/preferences", json={"maxNudgesPerDay": 2})
    assert r.status_code == 200
    assert r.json()["preferences"]["maxNudgesPerDay"] == 2


# --- chat -----------------------------------------------------------------

def test_chat_that_cannot_start_sends_an_error_event(client, monkeypatch):
    """With no API key the companion raises as it is built. That happened after
    the stream began and outside every handler, so the connection just dropped."""
    def no_key(*args, **kwargs):
        raise ValueError("No API key is configured.")
    monkeypatch.setattr(iris_api, "PersonalAICompanion", no_key)
    opened = client.post("/api/conversations").json()["id"]

    r = client.post(f"/api/conversations/{opened}/messages/stream", json={"text": "hello"})

    events = [json.loads(line[len("data:"):]) for line in r.text.splitlines() if line.startswith("data:")]
    assert events == [{"error": "No API key is configured.", "saved": False}]


# --- day counts -----------------------------------------------------------

def test_day_counts_use_the_local_calendar():
    now = datetime.now(UTC)
    assert _age_days(now) == 0
    assert _age_days(now - timedelta(days=1)) == 1
    local_midnight = datetime.combine(date.today(), datetime.min.time()).astimezone()
    assert _age_days(local_midnight.astimezone(UTC)) == 0, \
        "a moment today, stored in UTC, is still today"
    assert _age_days((local_midnight - timedelta(seconds=1)).astimezone(UTC)) == 1

"""The gate between noticing something and measuring it.

Discovery can propose whatever it likes; nothing it proposes counts until the
owner has read the quotes and said yes. These tests cover that seam from the
outside: what the review surface is given, what confirming and rejecting
actually do, and that neither can be done to someone else's writing.

Every entry below is invented.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from agent import constructs
from reading_fakes import every_quote_supports, is_support_check
from agent.database import db
from agent.observations import Citation, Observation
from agent.trackers.reflections import ReflectionService
from iris_api import app, get_current_user_id

CERTAIN = "I went all in on the opening I was most certain about and lost half the pieces."
AGAIN = "Doubled down again on the one game I felt sure of, and it went against me."
CLAIM = "The boldest moves appeared alongside the strongest expressions of certainty"


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def candidate(test_user, process_queue):
    """One construct staged for review, anchored in two real entries."""
    service = ReflectionService(test_user["id"])
    ids = {}
    for offset, text in ((120, CERTAIN), (80, AGAIN)):
        ids[text] = service.create_reflection(
            content=text, reflection_date=date.today() - timedelta(days=offset))
    process_queue()

    observation = Observation(
        claim=CLAIM,
        citations=(
            Citation(entry_id=ids[CERTAIN], entry_date=date.today() - timedelta(days=120),
                     text="I went all in on the opening I was most certain about"),
            Citation(entry_id=ids[AGAIN], entry_date=date.today() - timedelta(days=80),
                     text="Doubled down again on the one game I felt sure of"),
        ),
        span_start=date.today() - timedelta(days=120),
        span_end=date.today() - timedelta(days=80),
        entries_read=2,
        confidence_level="low",
    )
    return constructs.promote(test_user["id"], observation), ids


# --- what the owner is given to decide on -------------------------------------

def test_a_candidate_arrives_with_the_quotes_it_rests_on(client, candidate):
    theme_id, _ = candidate
    body = client.get("/api/constructs").json()

    found = [c for c in body["constructs"] if c["id"] == str(theme_id)]
    assert found, "the candidate is not on the review surface"
    assert found[0]["claim"] == CLAIM
    assert len(found[0]["quotes"]) == 2, "a claim without its evidence is not reviewable"
    assert all(q["text"] for q in found[0]["quotes"])


def test_a_quote_says_whether_it_can_become_evidence(client, candidate):
    quotes = client.get("/api/constructs").json()["constructs"][0]["quotes"]
    assert all(q["citable"] is True for q in quotes), "these came from dated entries"
    assert all(q["sourceType"] == "reflection" for q in quotes)


def test_only_candidates_are_reviewable(client, candidate):
    assert client.get("/api/constructs?status=active").status_code == 400


# --- confirming and rejecting -------------------------------------------------

def test_confirming_measures_it(client, candidate):
    theme_id, _ = candidate
    r = client.post(f"/api/constructs/{theme_id}/confirm")

    assert r.status_code == 200
    assert r.json()["status"] == "active"
    assert r.json()["occurrences"] >= 2, "the entries it was quoted from are occurrences"
    assert db.get_theme_by_id(theme_id)["status"] == "active"


def test_a_confirmed_construct_leaves_the_review_queue(client, candidate):
    theme_id, _ = candidate
    client.post(f"/api/constructs/{theme_id}/confirm")

    remaining = [c["id"] for c in client.get("/api/constructs").json()["constructs"]]
    assert str(theme_id) not in remaining


def test_rejecting_measures_nothing(client, candidate):
    theme_id, _ = candidate
    r = client.post(f"/api/constructs/{theme_id}/reject")

    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert db.get_theme_occurrences(theme_id) == []
    assert theme_id not in [t["id"] for t in db.get_themes(db.get_theme_by_id(theme_id)["user_id"])]


def test_an_unknown_construct_cannot_be_confirmed(client):
    assert client.post("/api/constructs/999999/confirm").status_code == 404
    assert client.post("/api/constructs/999999/reject").status_code == 404


def test_someone_elses_construct_is_not_actionable(client, candidate, test_user):
    """Single-user today, but the id comes from the URL: acting on a row without
    checking who owns it is the shape of the bug, whether or not it can fire."""
    theme_id, _ = candidate
    other = db.create_user(f"other_{test_user['username']}", "x")
    app.dependency_overrides[get_current_user_id] = lambda: other

    assert client.post(f"/api/constructs/{theme_id}/confirm").status_code == 404
    assert db.get_theme_by_id(theme_id)["status"] == "candidate", "untouched"


# --- discovery stages, it does not decide -------------------------------------

def test_discovery_stages_candidates_without_measuring_them(client, test_user, process_queue, monkeypatch):
    import json as _json

    service = ReflectionService(test_user["id"])
    ids = {}
    for offset, text in ((120, CERTAIN), (80, AGAIN)):
        ids[text] = service.create_reflection(
            content=text, reflection_date=date.today() - timedelta(days=offset))
    process_queue()

    payload = {"observations": [{
        "claim": CLAIM,
        "quotes": [
            {"entryId": ids[CERTAIN], "sourceType": "reflection",
             "text": "I went all in on the opening I was most certain about"},
            {"entryId": ids[AGAIN], "sourceType": "reflection",
             "text": "Doubled down again on the one game I felt sure of"},
        ],
    }]}

    class FakeModel:
        def chat(self, messages, system_prompt, **kwargs):
            if is_support_check(system_prompt):
                return every_quote_supports(messages)
            return _json.dumps(payload)

    monkeypatch.setattr("agent.observations.Intelligence", lambda *a, **kw: FakeModel())

    r = client.post("/api/constructs/discover", json={"includeStaged": False})
    assert r.status_code == 200
    staged = r.json()["constructs"]
    assert staged, "discovery found nothing to review"

    for c in staged:
        theme = db.get_theme_by_id(int(c["id"]))
        assert theme["status"] == "candidate", "discovery must not measure what it found"
        assert db.get_theme_occurrences(int(c["id"])) == []

"""API contract tests for the decision journal.

Any kind of decision, recorded when it is made: what is at stake and whether it
can be undone, how sure, what the days before held, what is pushing, sleep,
energy and feeling, and what would make the owner stop. Later: how it went, the
plan, and whether they would decide the same again. Asserts the wire shape the
frontend's `Decision` type expects, through the real routes and the test
database. Every entry here is invented.
"""

import pytest
from fastapi.testclient import TestClient

from iris_api import app, get_current_user_id

FULL = {
    "what": "Signed up for a marathon six weeks away",
    "decidedOn": "2024-05-10",
    "stake": "beyond_means",
    "reversible": "not_at_all",
    "confidence": 35,
    "lastDays": "setback",
    "pressures": ["deadline", "urge"],
    "sleepHours": 5.5,
    "energy": 3,
    "feeling": "frustrated",
    "plan": "Pull out if the long run in week three goes badly",
}


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_a_full_entry_comes_back_in_the_contract_shape(client):
    r = client.post("/api/decisions", json=FULL)
    assert r.status_code == 200, r.text
    d = r.json()
    for key, value in FULL.items():
        assert d[key] == value, key
    assert d["outcome"] is None and d["followedPlan"] is None
    assert d["wouldRepeat"] is None and d["closedAt"] is None
    assert isinstance(d["id"], str)


def test_only_what_is_required_so_a_hurried_entry_is_still_kept(client):
    """A journal that demands every answer in the moment gets skipped."""
    r = client.post("/api/decisions", json={"what": "Said yes to hosting the dinner"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["pressures"] == []
    assert d["stake"] is None and d["confidence"] is None and d["feeling"] is None
    assert d["decidedOn"]  # defaults to today


def test_a_pressure_named_twice_is_stored_once(client):
    d = client.post("/api/decisions", json={"what": "Moved the deadline",
                                            "pressures": ["people", "people"]}).json()
    assert d["pressures"] == ["people"]


@pytest.mark.parametrize("bad", [
    {"what": ""},
    {"what": "   "},
    {"what": "x", "stake": "enormous"},
    {"what": "x", "reversible": "maybe"},
    {"what": "x", "confidence": 101},
    {"what": "x", "confidence": -1},
    {"what": "x", "lastDays": "terrible"},
    {"what": "x", "pressures": ["boredom"]},
    {"what": "x", "energy": 11},
    {"what": "x", "sleepHours": 25},
    {"what": "x", "feeling": "fine"},
])
def test_values_that_cannot_be_read_back_are_refused(client, bad):
    r = client.post("/api/decisions", json=bad)
    assert r.status_code == 422, r.text


def test_the_list_is_newest_first(client):
    client.post("/api/decisions", json={"what": "older", "decidedOn": "2024-01-01"})
    client.post("/api/decisions", json={"what": "newer", "decidedOn": "2024-03-01"})
    whats = [d["what"] for d in client.get("/api/decisions").json()["decisions"]]
    assert whats.index("newer") < whats.index("older")


def test_recording_the_outcome_closes_the_decision(client):
    made = client.post("/api/decisions", json=FULL).json()
    r = client.patch(f"/api/decisions/{made['id']}", json={
        "outcome": "Finished, injured, three weeks off", "followedPlan": "no",
        "wouldRepeat": "no"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["outcome"] == "Finished, injured, three weeks off"
    assert d["followedPlan"] == "no" and d["wouldRepeat"] == "no"
    assert d["closedAt"] is not None


def test_how_it_went_and_whether_to_repeat_it_are_separate_answers(client):
    """A good decision can turn out badly; only the owner's judgement separates them."""
    made = client.post("/api/decisions", json={"what": "Took the slower, safer route"}).json()
    d = client.patch(f"/api/decisions/{made['id']}", json={
        "outcome": "Missed the start of the meeting", "wouldRepeat": "yes"}).json()
    assert d["wouldRepeat"] == "yes"


def test_correcting_an_outcome_keeps_the_day_it_closed(client):
    made = client.post("/api/decisions", json={"what": "Declined the invitation"}).json()
    first = client.patch(f"/api/decisions/{made['id']}", json={"outcome": "Quiet evening"}).json()
    second = client.patch(f"/api/decisions/{made['id']}",
                          json={"outcome": "Quiet evening, and glad of it", "wouldRepeat": "yes"}).json()
    assert second["closedAt"] == first["closedAt"]
    assert second["outcome"] == "Quiet evening, and glad of it"


def test_an_outcome_for_no_such_decision_is_a_404(client):
    r = client.patch("/api/decisions/999999", json={"outcome": "anything"})
    assert r.status_code == 404


@pytest.mark.parametrize("bad", [{"outcome": ""}, {"outcome": "  "},
                                 {"outcome": "x", "followedPlan": "mostly"},
                                 {"outcome": "x", "wouldRepeat": "probably"}])
def test_an_outcome_that_cannot_be_read_back_is_refused(client, bad):
    made = client.post("/api/decisions", json={"what": "Changed teams"}).json()
    assert client.patch(f"/api/decisions/{made['id']}", json=bad).status_code == 422

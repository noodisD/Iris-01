"""API contract tests for the decision log.

A log of risky commitments, recorded when one is made: how much was at stake as
a share of what the owner had, whether any was borrowed, what the days before
held, money needed soon, sleep and energy, the plan, and later the outcome.
Asserts the wire shape the frontend's `Decision` type expects, through the real
routes and the test database. Every entry here is invented: a chess club.
"""

import pytest
from fastapi.testclient import TestClient

from iris_api import app, get_current_user_id

FULL = {
    "what": "Entered every open tournament this month at once",
    "decidedOn": "2024-05-10",
    "sharePct": 140,
    "borrowed": True,
    "lastDays": "big_loss",
    "moneyNeededFor": "club membership",
    "moneyNeededBy": "2024-06-01",
    "sleepHours": 5.5,
    "energy": 3,
    "plan": "Withdraw after two losses in a row",
}


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_a_full_entry_comes_back_in_the_contract_shape(client):
    """Including a share above 100%: exactly the case worth seeing, so unbounded."""
    r = client.post("/api/decisions", json=FULL)
    assert r.status_code == 200, r.text
    d = r.json()
    for key, value in FULL.items():
        assert d[key] == value, key
    assert d["outcome"] is None and d["followedPlan"] is None and d["closedAt"] is None
    assert isinstance(d["id"], str)


def test_only_what_is_required_so_a_hurried_entry_is_still_kept(client):
    """A log that demands every field in the moment gets skipped."""
    r = client.post("/api/decisions", json={"what": "Played the gambit I never prepare"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["borrowed"] is False
    assert d["sharePct"] is None and d["lastDays"] is None and d["energy"] is None
    assert d["decidedOn"]  # defaults to today


@pytest.mark.parametrize("bad", [
    {"what": ""},
    {"what": "   "},
    {"what": "x", "energy": 11},
    {"what": "x", "energy": 0},
    {"what": "x", "sharePct": -1},
    {"what": "x", "sleepHours": 25},
    {"what": "x", "lastDays": "terrible"},
    {"what": "x", "moneyNeededBy": "2024-06-01"},
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
    r = client.patch(f"/api/decisions/{made['id']}",
                     json={"outcome": "Lost the first three and kept going", "followedPlan": "no"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["outcome"] == "Lost the first three and kept going"
    assert d["followedPlan"] == "no"
    assert d["closedAt"] is not None


def test_correcting_an_outcome_keeps_the_day_it_closed(client):
    made = client.post("/api/decisions", json={"what": "Offered a draw early"}).json()
    first = client.patch(f"/api/decisions/{made['id']}", json={"outcome": "Draw"}).json()
    second = client.patch(f"/api/decisions/{made['id']}",
                          json={"outcome": "Draw, and glad of it", "followedPlan": "yes"}).json()
    assert second["closedAt"] == first["closedAt"]
    assert second["outcome"] == "Draw, and glad of it"


def test_an_outcome_for_no_such_decision_is_a_404(client):
    r = client.patch("/api/decisions/999999", json={"outcome": "anything"})
    assert r.status_code == 404


@pytest.mark.parametrize("bad", [{"outcome": ""}, {"outcome": "  "},
                                 {"outcome": "x", "followedPlan": "mostly"}])
def test_an_outcome_that_cannot_be_read_back_is_refused(client, bad):
    made = client.post("/api/decisions", json={"what": "Resigned a lost position"}).json()
    assert client.patch(f"/api/decisions/{made['id']}", json=bad).status_code == 422

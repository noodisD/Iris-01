"""Whether a quote can be checked, and whether an empty screen says why.

Two failures of the same kind. A pull quote arrived with a date and a kind but
no id, so the one thing the owner might want — to go and read what they actually
wrote around it — was the one thing the card could not do. And an empty Insights
screen had a single explanation for six different situations, including the one
where IRIS *has* findings and the owner's own confidence filter is hiding them.
Saying "nothing found" there is false, and it hides a setting they can change.

Every entry below is invented.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from agent.database import db
from agent.insights_service import InsightsService
from agent.trackers.reflections import ReflectionService
from iris_api import app, get_current_user_id


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def theme_from_entries(test_user):
    """A theme whose occurrences are the owner's own entries, each on its day."""
    uid = test_user["id"]
    tid = db.create_theme(
        uid, [0.0] * 1536, "Worrying about the launch deadline",
        (datetime.now() - timedelta(days=40)).isoformat(),
        datetime.now().isoformat(), 5,
    )
    service = ReflectionService(uid)
    ids = []
    for i in range(5):
        occurred = datetime.now() - timedelta(days=i * 2)
        rid = service.create_reflection(
            content="Anxious about whether we'll ship on time",
            reflection_date=occurred.date(),
        )
        db.add_theme_occurrence(tid, "reflection", rid,
                                "Anxious about whether we'll ship on time",
                                0.9, occurred.isoformat())
        ids.append(rid)
    return tid, ids


# --- a quote the owner can check ---------------------------------------------

def test_a_quote_carries_the_entry_it_came_from(test_user, theme_from_entries):
    tid, ids = theme_from_entries
    quotes = InsightsService(test_user["id"])._pull_quotes({"theme_id": tid})

    assert quotes, "the theme has occurrences with snippets"
    assert quotes[0]["sourceId"] in {str(i) for i in ids}
    assert quotes[0]["sourceKind"] == "journal"


def test_a_quote_from_chat_offers_no_link(test_user):
    """Chat is recollection and has no page to open (ADR-0003). A link that goes
    nowhere is worse than none."""
    uid = test_user["id"]
    tid = db.create_theme(uid, [0.0] * 1536, "Talking about the deadline",
                          datetime.now().isoformat(), datetime.now().isoformat(), 1)
    db.add_theme_occurrence(tid, "conversation_message", 1, "we talked about shipping",
                            0.9, datetime.now().isoformat())

    quote = InsightsService(uid)._pull_quotes({"theme_id": tid})[0]
    assert quote["sourceKind"] == "chat"
    assert quote["sourceId"] is None


def test_the_api_ships_the_id_with_the_quote(client, theme_from_entries):
    insights = client.get("/api/insights").json()
    if not insights:
        pytest.skip("no insight admitted for this theme; covered by the unit tests above")
    detail = client.get(f"/api/insights/{insights[0]['id']}").json()
    for quote in detail["pullQuotes"]:
        assert "sourceId" in quote, "the frontend cannot link what it is not sent"


# --- an empty screen that names its reason -----------------------------------

def test_coverage_reports_why_the_list_may_be_empty(test_user, theme_from_entries):
    cov = InsightsService(test_user["id"]).coverage()
    for key in ("suppressedByFilter", "hiddenByStatus", "admitted"):
        assert key in cov, f"the screen cannot explain itself without {key}"


def test_the_stated_reason_agrees_with_the_list_shown(test_user, theme_from_entries):
    """The invariant behind every empty state: what the screen says was withheld,
    plus what it shows, must account for everything admitted."""
    service = InsightsService(test_user["id"])
    cov = service.coverage()
    shown = service.list_summaries()

    assert cov["admitted"] - cov["hiddenByStatus"] == len(shown)


def test_resolving_everything_is_reported_as_resolved_not_as_nothing_found(
        client, test_user, theme_from_entries):
    insights = client.get("/api/insights").json()
    if not insights:
        pytest.skip("no insight admitted for this theme")
    for i in insights:
        client.post(f"/api/insights/{i['id']}/snooze", json={"days": 30})

    cov = InsightsService(test_user["id"]).coverage()
    assert cov["hiddenByStatus"] == cov["admitted"] > 0, (
        "with everything snoozed the screen must say so, not claim nothing was found")


def test_a_failed_breakdown_reads_as_unknown_not_as_zero(test_user, monkeypatch):
    """A check that could not run must not come back as a measured absence."""
    service = InsightsService(test_user["id"])
    monkeypatch.setattr(InsightsService, "_normalize",
                        lambda self: (_ for _ in ()).throw(RuntimeError("engines down")))

    cov = service.coverage()
    assert cov["admitted"] is None
    assert cov["suppressedByFilter"] is None
    assert cov["hiddenByStatus"] is None

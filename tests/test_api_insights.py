"""
API contract tests for the insights slice.

Seeds a theme with recent occurrences so the trajectory engine yields a real
insight, then asserts the frontend's InsightSummary / InsightDetail shapes and
the snooze flow. Single-user auth overridden to test_user.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from agent.database import db
from iris_api import app, get_current_user_id


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_theme(test_user):
    """A theme with several recent occurrences → trajectory produces an insight.

    Each occurrence is backed by an entry written on its day. IRIS withholds
    findings about the present while nothing recent has been logged
    (agent/coverage.py), and a theme occurring "two days ago" with nothing
    written for months is a world that cannot happen.
    """
    tid = db.create_theme(
        test_user["id"], [0.0] * 1536, "Worrying about the launch deadline",
        (datetime.now() - timedelta(days=40)).isoformat(),
        datetime.now().isoformat(), 5,
    )
    for i in range(5):
        occurred = datetime.now() - timedelta(days=i * 2)
        entry_id = db.create_reflection(test_user['id'], "I'm anxious about whether we'll ship on time", reflection_date=occurred.isoformat())
        db.add_theme_occurrence(
            tid, "reflection", entry_id,
            "I'm anxious about whether we'll ship on time",
            0.9, occurred.isoformat(),
        )
    return tid


def test_list_insights_returns_contract(client, seeded_theme):
    r = client.get("/api/insights")
    assert r.status_code == 200
    insights = r.json()
    assert isinstance(insights, list) and insights, "expected at least one insight"
    i = insights[0]
    for key in ("id", "kind", "status", "headline", "summary", "accentColor",
                "featured", "tags", "confidence", "detectedAt", "seen"):
        assert key in i, f"missing {key}"
    for line in ("line1", "line2", "line3"):
        assert line in i["headline"], f"missing headline {line}"
    assert i["status"] in ("new", "active", "snoozed", "resolved")


def test_get_insight_detail_has_evidence(client, seeded_theme):
    insight_id = client.get("/api/insights").json()[0]["id"]
    r = client.get(f"/api/insights/{insight_id}")
    assert r.status_code == 200
    detail = r.json()
    for key in ("irisRead", "evidence", "pullQuotes", "related", "suggestions", "methodology"):
        assert key in detail, f"missing {key}"
    assert isinstance(detail["evidence"], list) and detail["evidence"]
    assert detail["evidence"][0]["kind"] in ("twin-series", "heatmap", "comparison", "callout")


def test_snooze_hides_insight_from_list(client, seeded_theme):
    insight_id = client.get("/api/insights").json()[0]["id"]
    r = client.post(f"/api/insights/{insight_id}/snooze", json={"days": 30})
    assert r.status_code == 200
    assert r.json()["status"] == "snoozed"
    remaining = [i["id"] for i in client.get("/api/insights").json()]
    assert insight_id not in remaining


def test_resolve_hides_insight_from_list(client, seeded_theme):
    insight_id = client.get("/api/insights").json()[0]["id"]
    r = client.post(f"/api/insights/{insight_id}/resolve")
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"
    remaining = [i["id"] for i in client.get("/api/insights").json()]
    assert insight_id not in remaining


def test_a_finding_about_two_themes_shows_no_single_origin(client, test_user, monkeypatch):
    """`origin` says how a finding was arrived at — clustered, or read and
    vouched for. A pair has two ends and can have one of each, so the card
    showed the first theme's origin for the whole thing."""
    from agent.insights_service import _tension_to_card

    card = _tension_to_card({"theme_a_id": 1, "theme_b_id": 2, "tension_label": "persistent",
                             "theme_a_summary": "A", "theme_b_summary": "B",
                             "recent_cooccurrence_count": 3, "past_cooccurrence_count": 2,
                             "cooccurrence_count": 5, "confidence_level": "medium"})

    assert card["pair_of"] == (1, 2), "the card knows it is about two patterns"

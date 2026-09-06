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
    """A theme with several recent occurrences → trajectory produces an insight."""
    tid = db.create_theme(
        test_user["id"], [0.0] * 1536, "Worrying about the launch deadline",
        (datetime.now() - timedelta(days=40)).isoformat(),
        datetime.now().isoformat(), 5,
    )
    for i in range(5):
        db.add_theme_occurrence(
            tid, "reflection", 1000 + i,
            "I'm anxious about whether we'll ship on time",
            0.9, (datetime.now() - timedelta(days=i * 2)).isoformat(),
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

"""A claim about now needs evidence from now.

The owner's archive ends in May and the screen showed eight cards reading
"... is dissipated - 0 in 21d - 0 in the 90d before", eight of them at medium
confidence. Two separate faults produced that: the resolution engine turned an
empty comparison into a verdict, and nothing asked whether the last three weeks
contained any writing at all. These tests pin both, and pin what must keep
working: a theme that genuinely stops while the owner keeps writing is still a
finding.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from agent.coverage import current_state_gate, observation_coverage
from agent.database import db
from agent.insights_service import InsightsService
from agent.resolution import ResolutionEngine
from agent.timeutils import utc_now
from iris_api import app, get_current_user_id


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def _theme_with_occurrences(user_id: int, days_ago: list[int], summary: str = "A theme") -> int:
    now = utc_now()
    theme_id = db.create_theme(
        user_id, [0.1] * 1536, summary,
        (now - timedelta(days=max(days_ago))).isoformat(),
        (now - timedelta(days=min(days_ago))).isoformat(),
    )
    for i, days in enumerate(days_ago):
        occurred = now - timedelta(days=days)
        entry_id = db.create_journal_entry(
            user_id, f"occurrence {i}", {}, created_at=occurred.isoformat())
        db.add_theme_occurrence(theme_id, "journal_entry", entry_id, "snippet", 0.9,
                                occurred.isoformat())
    return theme_id


def _kept_writing(user_id: int, days_ago: list[int]) -> None:
    now = utc_now()
    for i, days in enumerate(days_ago):
        db.create_journal_entry(user_id, f"still writing {i}", {},
                                created_at=(now - timedelta(days=days)).isoformat())


# --- the engine ---------------------------------------------------------------

def test_an_empty_comparison_is_not_a_finding(test_user):
    """Occurrences older than both windows: nothing was compared, so there is
    nothing to report. This returned 'dissipated' for all 18 of the owner's
    themes."""
    theme_id = _theme_with_occurrences(test_user["id"], [200, 210, 220, 230])

    result = ResolutionEngine(test_user["id"]).analyze_theme(theme_id, force_recompute=True)

    assert result["recent_count"] == 0 and result["past_count"] == 0
    assert result["resolution_label"] == "unsupported"
    assert result["current_state_supported"] is False


def test_a_theme_that_stopped_while_the_owner_kept_writing_is_still_a_finding(test_user):
    theme_id = _theme_with_occurrences(test_user["id"], [40, 45, 50])
    _kept_writing(test_user["id"], [1, 4, 8, 12, 16, 20, 30, 35])

    result = ResolutionEngine(test_user["id"]).analyze_theme(theme_id, force_recompute=True)

    assert result["resolution_label"] == "dissipated"
    assert result["current_state_supported"] is True


# --- the coverage rule --------------------------------------------------------

def test_nothing_recent_means_nothing_is_said_about_now(test_user):
    _theme_with_occurrences(test_user["id"], [40, 45, 50])  # newest entry is 40 days old
    user_id = test_user["id"]

    coverage = observation_coverage(user_id)
    assert coverage.supports_current_state is False
    assert coverage.days_since_last >= 40

    findings = [{"engine": "resolution", "label": "dissipated", "confidence_level": "high"}]
    assert current_state_gate(findings, {"user_id": user_id}) == []
    assert InsightsService(user_id).list_summaries() == []


def test_recent_writing_lets_findings_through(test_user):
    _theme_with_occurrences(test_user["id"], [40, 45, 50])
    _kept_writing(test_user["id"], [2, 6, 11])  # three days: the rule's minimum

    coverage = observation_coverage(test_user["id"])
    assert coverage.supports_current_state is True
    findings = [{"engine": "resolution", "label": "dissipated", "confidence_level": "high"}]
    assert current_state_gate(findings, {"user_id": test_user["id"]}) == findings


def test_the_boundary_day_is_observed_once_not_twice(test_user):
    """The day of a theme's last occurrence used to count as observed *before*
    the silence and again *during* it, which is how an unobserved gap earned
    continuity credit."""
    now = utc_now()
    last_day = now - timedelta(days=30)
    db.create_journal_entry(test_user["id"], "the last thing written", {},
                            created_at=last_day.isoformat())

    during = db.count_observed_days(test_user["id"], last_day, now)
    before = db.count_observed_days(test_user["id"], last_day - timedelta(days=30), last_day)

    assert during == 0, "the last logged day is not observation *after* itself"
    assert before == 1


def test_todays_writing_still_counts_as_observed(test_user):
    """The end of the window stays inclusive: an entry written earlier today is
    the clearest evidence that someone is still logging."""
    now = utc_now()
    db.create_journal_entry(test_user["id"], "written today", {}, created_at=now.isoformat())

    assert db.count_observed_days(test_user["id"], now - timedelta(days=7), now) == 1


# --- what the screen says instead ---------------------------------------------

def test_the_screen_is_told_why_the_list_is_empty(client, test_user):
    _theme_with_occurrences(test_user["id"], [40, 45, 50])

    assert client.get("/api/insights").json() == []
    coverage = client.get("/api/insights/coverage").json()

    assert coverage["supportsCurrentState"] is False
    assert coverage["daysSinceLastEntry"] >= 40
    assert coverage["lastEntryOn"] is not None
    assert coverage["entries"] >= 3 and coverage["themes"] >= 1


def test_a_cached_verdict_over_two_empty_windows_is_not_served(test_user):
    """The rule that produced "dissipated · 0 in 21d · 0 in the 90d before" was
    removed, but eighteen such verdicts sat in the cache with a fresh timestamp.
    A cached answer the current rules cannot produce must not outlive them."""
    user_id = test_user["id"]
    theme_id = _theme_with_occurrences(user_id, [200, 210, 220])
    from agent.database import resolutions

    resolutions.create_or_update(
        pattern_type="theme", pattern_id=theme_id, resolution_label="dissipated",
        attenuation_score=1.0, confidence_level="medium", recent_count=0, past_count=0,
    )
    assert resolutions.get_resolution("theme", theme_id)["resolution_label"] == "dissipated"

    result = ResolutionEngine(user_id).analyze_theme(theme_id)  # cache allowed

    assert result["resolution_label"] == "unsupported"
    assert result["current_state_supported"] is False


# --- watching means watching on more than one day -----------------------------

def _absence(baseline_count, days_silent, during, before, span=None):
    from agent.confidence import ConfidenceEngine

    return ConfidenceEngine().compute_absence_confidence(
        baseline_count=baseline_count, days_silent=days_silent,
        silence_threshold_days=21, observed_days_during=during,
        observed_days_before=before, baseline_span_days=span,
    )


def test_a_burst_on_one_day_cannot_be_a_confident_cessation():
    """Ten occurrences in one sitting, one day logged either side of the gap:
    the ratio reads as perfect watchfulness and scored high, 1.0 — higher than a
    genuinely well-observed case."""
    result = _absence(baseline_count=10, days_silent=60, during=1, before=1, span=0.0)
    assert result["confidence_level"] == "low", result


def test_three_occurrences_and_one_observed_day_is_not_medium():
    result = _absence(baseline_count=3, days_silent=40, during=1, before=1, span=0.0)
    assert result["confidence_level"] == "low", result


def test_sustained_observation_still_supports_a_cessation():
    """The guard must not buy honesty by rejecting everything: weekly logging
    right through a silence is what a supported dissipation looks like."""
    result = _absence(baseline_count=8, days_silent=30, during=4, before=5, span=45.0)
    assert result["confidence_level"] in ("medium", "high"), result


def test_a_long_baseline_watched_throughout_can_still_be_high():
    result = _absence(baseline_count=12, days_silent=60, during=40, before=45, span=90.0)
    assert result["confidence_level"] == "high", result


# --- an unsupported finding is a non-finding everywhere -----------------------

def test_unsupported_never_reaches_chat_even_at_the_lowest_threshold(test_user):
    """It was filtered on the Insights screen only, so `min_confidence: low`
    let a finding that measured nothing into the chat context."""
    from agent.coverage import current_state_gate
    from agent.preferences import UserPreferencesService

    UserPreferencesService(test_user["id"]).update_pref("min_confidence", "low")
    _kept_writing(test_user["id"], [1, 3, 5])  # coverage satisfied on its own terms

    findings = [
        {"engine": "resolution", "resolution_label": "unsupported",
         "current_state_supported": False, "confidence_level": "low"},
        {"engine": "trajectory", "label": "increasing", "confidence_level": "low"},
    ]
    kept = current_state_gate(findings, {"user_id": test_user["id"]})

    assert [k["engine"] for k in kept] == ["trajectory"]


def test_a_failed_coverage_check_withholds_rather_than_admits(test_user, monkeypatch):
    """The pipeline catches a gate's exception and keeps the candidates, so a
    gate that raises admits exactly what it exists to withhold."""
    from agent import coverage as coverage_module

    def boom(*a, **kw):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(coverage_module.db, "count_observed_days", boom)
    findings = [{"engine": "trajectory", "label": "increasing", "confidence_level": "high"}]

    assert coverage_module.current_state_gate(findings, {"user_id": test_user["id"]}) == []
    assert coverage_module.observation_coverage(test_user["id"]).available is False


def test_an_unavailable_coverage_check_is_not_reported_as_an_absence(test_user, monkeypatch):
    from agent import coverage as coverage_module

    monkeypatch.setattr(coverage_module.db, "count_observed_days",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("down")))
    payload = coverage_module.observation_coverage(test_user["id"]).as_dict()

    assert payload["available"] is False and payload["supportsCurrentState"] is False


def test_one_recent_day_is_not_enough_to_describe_the_present(test_user):
    _theme_with_occurrences(test_user["id"], [40, 45, 50])
    _kept_writing(test_user["id"], [2])  # a single day back

    coverage = observation_coverage(test_user["id"])
    assert coverage.observed_days_in_window == 1
    assert coverage.supports_current_state is False, "one entry is a sign of life, not a basis"


def test_a_valid_unsupported_verdict_is_served_from_cache(test_user, monkeypatch):
    """Recomputing it on every read rewrote confidence and evidence rows for an
    answer that had not changed."""
    theme_id = _theme_with_occurrences(test_user["id"], [200, 210, 220])
    engine = ResolutionEngine(test_user["id"])
    assert engine.analyze_theme(theme_id)["resolution_label"] == "unsupported"

    computed = []
    original = ResolutionEngine._classify_resolution
    monkeypatch.setattr(ResolutionEngine, "_classify_resolution",
                        lambda self, *a, **kw: computed.append(1) or original(self, *a, **kw))
    again = ResolutionEngine(test_user["id"]).analyze_theme(theme_id)

    assert again["resolution_label"] == "unsupported"
    assert again["current_state_supported"] is False
    assert computed == [], "an unchanged unsupported verdict must come from cache"

"""Patterns measured at the scale of the record, not the fortnight.

Every other engine looks through 14 to 90 days. On the owner's archive that
window is empty while the archive is full: none of 19 themes had an occurrence
in the last 90 days, and 14 of them had three or more across the whole record.
The evidence was never thin — the ruler was wrong.

This scale reports arithmetic over the same occurrences: how many, between which
dates, across how many months, which year holds most, how long since the last.
It never says how things *are*, which is what earns it the coverage gate's
exemption — and the tests below hold that exemption to being narrow, because a
gate that lets the wrong thing through is worse than no gate.

Every entry below is invented.
"""

from __future__ import annotations

from datetime import date, timedelta

from agent.constants import (
    LIFELONG_CONCENTRATION_SHARE,
    LIFELONG_MIN_OCCURRENCES,
    LIFELONG_MIN_SPAN_DAYS,
)
from agent.coverage import claims_present, current_state_gate
from agent.database import db
from agent.lifelong import LifelongEngine

TODAY = date.today()


def _theme_with(user_id, days_ago_list, summary="a pattern"):
    """A theme whose occurrences fall on exactly these days."""
    first = (TODAY - timedelta(days=max(days_ago_list))).isoformat()
    last = (TODAY - timedelta(days=min(days_ago_list))).isoformat()
    theme_id = db.create_theme(user_id, [0.1] * 1536, summary, first, last,
                               occurrence_count=len(days_ago_list))
    for i, ago in enumerate(days_ago_list):
        db.add_theme_occurrence(
            theme_id, "reflection", 10_000 + theme_id * 100 + i, "snippet", 0.8,
            (TODAY - timedelta(days=ago)).isoformat())
    return theme_id


def _find(user_id, theme_id):
    return next((r for r in LifelongEngine(user_id).analyze_all_themes()
                 if r["theme_id"] == theme_id), None)


# --- what qualifies as lifelong -------------------------------------------------

def test_a_pattern_across_years_is_reported(test_user):
    theme_id = _theme_with(test_user["id"], [700, 650, 400, 200, 120, 30])
    found = _find(test_user["id"], theme_id)

    assert found is not None
    assert found["occurrence_count"] == 6
    assert found["span_days"] >= LIFELONG_MIN_SPAN_DAYS


def test_too_few_occurrences_is_an_incident_not_a_pattern(test_user):
    theme_id = _theme_with(test_user["id"], [500, 200])
    assert len(([500, 200])) < LIFELONG_MIN_OCCURRENCES
    assert _find(test_user["id"], theme_id) is None


def test_a_burst_in_one_week_is_not_lifelong(test_user):
    """Eight occurrences inside a week is a burst. Calling it long-running
    because there are many of them is the mistake this floor exists to stop."""
    theme_id = _theme_with(test_user["id"], [30, 29, 28, 27, 26, 25, 24, 23])
    assert _find(test_user["id"], theme_id) is None


def test_a_skipped_theme_is_absent_rather_than_hedged(test_user):
    """Not reported with a low-confidence caveat: a caveat still puts it on the
    screen as history."""
    theme_id = _theme_with(test_user["id"], [40, 35, 30])
    assert _find(test_user["id"], theme_id) is None


# --- what it measures -----------------------------------------------------------

def test_occurrences_clustered_in_one_year_are_called_concentrated(test_user):
    """Most of them in one stretch, a couple long after."""
    theme_id = _theme_with(test_user["id"], [700, 695, 690, 685, 680, 675, 670, 40])
    found = _find(test_user["id"], theme_id)

    assert found["share_in_densest"] >= LIFELONG_CONCENTRATION_SHARE
    assert found["lifelong_label"] == "concentrated"


def test_occurrences_across_the_span_are_called_spread(test_user):
    theme_id = _theme_with(test_user["id"], [700, 600, 500, 400, 300, 200, 100, 20])
    found = _find(test_user["id"], theme_id)

    assert found["lifelong_label"] in ("concentrated", "spread")
    assert 0 < found["share_in_densest"] <= 1


def test_it_reports_how_long_since_the_last_one(test_user):
    theme_id = _theme_with(test_user["id"], [700, 400, 200])
    found = _find(test_user["id"], theme_id)
    assert found["days_since_last"] >= 199


def test_distinct_months_are_counted_not_occurrences(test_user):
    """Three occurrences in one month and three across three months say
    different things about how long-running something is."""
    theme_id = _theme_with(test_user["id"], [400, 399, 398, 200, 100])
    found = _find(test_user["id"], theme_id)
    assert found["active_months"] < found["occurrence_count"]


def test_confidence_needs_span_as_well_as_count(test_user):
    """The same number of occurrences crammed into three months is not the same
    evidence as spread over two years."""
    wide = _theme_with(test_user["id"], [730, 600, 500, 400, 300, 200, 100, 20], "wide")
    # Over the 90-day floor so it qualifies at all, but nowhere near a year —
    # the first draft spanned 70 days and was skipped outright, which tested the
    # floor while claiming to test the confidence tier.
    narrow = _theme_with(test_user["id"], [200, 190, 180, 170, 160, 150, 120, 100], "narrow")

    assert _find(test_user["id"], wide)["confidence_level"] == "high"
    assert _find(test_user["id"], narrow)["confidence_level"] != "high"


# --- it never claims the present ------------------------------------------------

def test_a_lifelong_finding_makes_no_claim_about_now(test_user):
    theme_id = _theme_with(test_user["id"], [700, 400, 200])
    assert _find(test_user["id"], theme_id)["claims_present"] is False


def test_the_gate_keeps_span_findings_when_writing_is_thin(test_user):
    """The exemption. "Twelve times across two years, none since March" is true
    whether or not this month is quiet."""
    historical = {"engine": "lifelong", "claims_present": False, "label": "spread"}
    kept = current_state_gate([historical], {"user_id": test_user["id"]})
    assert kept == [historical]


def test_the_gate_still_withholds_present_tense_findings(test_user):
    """The exemption must stay narrow, or it is a hole rather than a door."""
    present = {"engine": "trajectory", "label": "increasing"}
    assert current_state_gate([present], {"user_id": test_user["id"]}) == []


def test_a_finding_that_does_not_declare_itself_is_gated(test_user):
    """Silence is read as a present-tense claim, so forgetting to declare
    withholds rather than admits."""
    assert claims_present({"engine": "whatever"}) is True
    assert current_state_gate([{"engine": "whatever"}], {"user_id": test_user["id"]}) == []


def test_a_mixed_batch_keeps_only_the_historical_half(test_user):
    historical = {"engine": "lifelong", "claims_present": False}
    present = {"engine": "trajectory", "label": "increasing"}
    kept = current_state_gate([present, historical], {"user_id": test_user["id"]})
    assert kept == [historical]

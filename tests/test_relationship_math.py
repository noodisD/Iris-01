"""
Leverage reports a conditional probability, so it must behave like one.

analyze_pair counted *pairs* of (source, target) occurrences within the lag
window and then divided by the number of source events. One source event
followed by three target events contributed 3 to the numerator and 1 to the
denominator, so P(target | source) could exceed 1 — and the denser the target
theme, the more inflated the association. Since the value is also clamped into
an influence score and compared against a threshold, dense themes looked
causally linked to everything.

The quantity that is actually meaningful is: of the times this theme occurred,
how often was it followed by the other within the lag.
"""

from datetime import timedelta

import pytest

from agent.leverage import LeverageEngine
from agent.timeutils import utc_now


class _StubConfidence:
    @staticmethod
    def compute_confidence(*_a, **_k):
        return {"confidence_level": "high", "confidence_score": 0.9, "data_points_count": 3,
                "time_coverage_days": 11, "consistency_score": 0.9, "recency_score": 0.9}


class _StubEvidence:
    @staticmethod
    def record_evidence(*_a, **_k):
        return None


@pytest.fixture
def engine(monkeypatch):
    """A leverage engine with its persistence and confidence boundaries stubbed,
    so the arithmetic under test is the only thing exercised."""
    eng = LeverageEngine.__new__(LeverageEngine)
    eng.user_id = 1
    eng._evidence = []
    eng.conf_engine = _StubConfidence()
    eng.ev_engine = _StubEvidence()
    monkeypatch.setattr("agent.leverage.confidence_repo.create_or_update", lambda *a, **k: None)
    monkeypatch.setattr("agent.leverage.leverage_repo.create_or_update_pair", lambda *a, **k: None)
    return eng


def _at(*days_ago):
    now = utc_now()
    return [now - timedelta(days=d) for d in days_ago]


def test_probability_cannot_exceed_one(engine, monkeypatch):
    """Five source events, each followed by three target events.

    Counting pairs makes the numerator larger than the number of source events,
    so P(target | source) exceeded 1 and the influence score saturated.
    """
    source = _at(30, 25, 20, 15, 10)
    target = _at(29, 28, 27, 24, 23, 22, 19, 18, 17, 14, 13, 12, 9, 8, 7)

    monkeypatch.setattr(engine, "_get_occurrences",
                        lambda kind, ident, since: source if ident == 1 else target)

    result = engine.analyze_pair("theme", 1, "theme", 2)
    assert result is not None
    assert -1.0 <= result["directional_lift"] <= 1.0, (
        f"lift is a difference of two probabilities and must lie in [-1, 1], "
        f"got {result['directional_lift']}"
    )


def test_a_relation_that_always_holds_scores_one(engine, monkeypatch):
    """Five source events, each followed the next day by exactly one target,
    spaced far enough apart that no target is followed by the *next* source
    inside the lag window. So P(target|source) = 1, P(source|target) = 0."""
    source = _at(45, 36, 27, 18, 9)
    target = _at(44, 35, 26, 17, 8)

    monkeypatch.setattr(engine, "_get_occurrences",
                        lambda kind, ident, since: source if ident == 1 else target)

    result = engine.analyze_pair("theme", 1, "theme", 2)
    assert result is not None
    assert result["directional_lift"] == pytest.approx(1.0), (
        f"every source is followed and no target is preceded, so the lift is 1.0; "
        f"got {result['directional_lift']}"
    )


def test_a_symmetric_relation_has_no_direction(engine, monkeypatch):
    """When each theme follows the other equally often, neither leads."""
    source = _at(40, 30, 20, 10, 5)
    target = _at(39, 29, 19, 9, 4)
    # Same shape both ways: swap the roles and the lift must invert.
    monkeypatch.setattr(engine, "_get_occurrences",
                        lambda kind, ident, since: source if ident == 1 else target)
    forward = engine.analyze_pair("theme", 1, "theme", 2)["directional_lift"]
    monkeypatch.setattr(engine, "_get_occurrences",
                        lambda kind, ident, since: target if ident == 1 else source)
    backward = engine.analyze_pair("theme", 1, "theme", 2)["directional_lift"]
    assert forward == pytest.approx(-backward), (
        f"swapping source and target must invert the lift, got {forward} and {backward}"
    )

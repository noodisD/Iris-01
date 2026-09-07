"""
Trajectory must measure a change in rate, not an accumulation of events.

The slope regressed *cumulative count* against time. A cumulative count only
ever rises, so the slope was positive for every real series: a constant cadence
of one entry a day scored +1.0, and even a clearly decelerating series scored
+0.14. Since the classifier falls through to the slope whenever the recent
frequency is close to the baseline — which is exactly the definition of a
stable pattern — "stable" was effectively unreachable and steady habits were
reported back to the user as "increasing".

These series are hand-constructed so the correct answer is not in doubt.
"""

from datetime import timedelta

import pytest

from agent.timeutils import utc_now
from agent.trajectory import TrajectoryEngine


@pytest.fixture
def engine():
    return TrajectoryEngine.__new__(TrajectoryEngine)


def _series(days_ago):
    """Reflections at the given ages, all of equal evidence weight."""
    now = utc_now()
    return [
        {"occurred_at": now - timedelta(days=d), "source_type": "reflection", "snippet": ""}
        for d in days_ago
    ]


def test_a_constant_cadence_has_no_trend(engine):
    """One entry a day for eight weeks. The rate never changes, so the slope
    must be ~0 — this is the case that used to score +1.0."""
    slope = engine._calculate_trend_slope(_series(list(range(56))))
    assert abs(slope) < 0.05, f"a constant cadence should show no trend, got {slope:+.4f}"


def test_an_accelerating_series_has_a_positive_trend(engine):
    """Sparse eight weeks ago, dense this week."""
    days = [55, 48, 41, 34] + [6, 5, 4, 3, 2, 1, 0]
    slope = engine._calculate_trend_slope(_series(days))
    assert slope > 0.05, f"a rising cadence should show a positive trend, got {slope:+.4f}"


def test_a_decelerating_series_has_a_negative_trend(engine):
    """Dense eight weeks ago, sparse now — the case that used to score +0.14."""
    days = [55, 54, 53, 52, 51, 50, 49] + [20, 10]
    slope = engine._calculate_trend_slope(_series(days))
    assert slope < -0.05, f"a falling cadence should show a negative trend, got {slope:+.4f}"


def test_the_sign_is_symmetric(engine):
    """The same shape reversed in time must reverse the sign."""
    rising = [55, 48, 41, 34, 6, 5, 4, 3, 2, 1, 0]
    falling = [55 - d for d in rising]
    up = engine._calculate_trend_slope(_series(rising))
    down = engine._calculate_trend_slope(_series(falling))
    assert up > 0 > down, f"expected opposite signs, got {up:+.4f} and {down:+.4f}"


def test_too_little_history_claims_no_trend(engine):
    """Everything inside a single bucket cannot evidence a direction."""
    assert engine._calculate_trend_slope(_series([2, 1, 0])) == 0.0
    assert engine._calculate_trend_slope(_series([])) == 0.0


def test_weighting_still_favours_richer_evidence(engine):
    """A reflection (1.0) should move the trend more than a bare habit tick (0.5)."""
    now = utc_now()
    recent_reflection = [
        {"occurred_at": now - timedelta(days=d), "source_type": "reflection", "snippet": ""}
        for d in (40, 39, 3)
    ]
    recent_tick = [
        {"occurred_at": now - timedelta(days=d), "source_type": "habit_completion", "snippet": ""}
        if d == 3 else
        {"occurred_at": now - timedelta(days=d), "source_type": "reflection", "snippet": ""}
        for d in (40, 39, 3)
    ]
    assert engine._calculate_trend_slope(recent_reflection) >= engine._calculate_trend_slope(recent_tick)

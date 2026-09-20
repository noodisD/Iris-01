
from datetime import datetime, timedelta

from agent.database import db
from agent.leverage import LeverageEngine
from agent.trajectory import TrajectoryEngine


def test_trajectory_slope_math(test_user, freeze_time):
    user_id = test_user['id']
    engine = TrajectoryEngine(user_id)

    # Teleport to fixed time
    base_time = datetime(2026, 1, 1)
    freeze_time.set_time(base_time)

    theme_id = db.create_theme(user_id, [0.1]*1536, "Math Theme", base_time.isoformat(), base_time.isoformat())

    # 1. Create a perfectly linear increasing trend
    # Day 0: 1 occ
    # Day 10: 1 occ
    # Day 20: 1 occ
    # (Simplified: linear regression on indices [0, 10, 20] vs values [1, 2, 3])
    for i in range(3):
        occ_time = base_time + timedelta(days=i*10)
        db.add_theme_occurrence(theme_id, 'reflection', 100+i, "snippet", 0.9, occ_time.isoformat())
        db.update_theme_stats(theme_id, occ_time.isoformat())

    # Move 'now' forward so windows establish correctly
    # Baseline: 60d, Recent: 14d (Trajectory Engine constants)
    freeze_time.set_time(base_time + timedelta(days=30))

    analysis = engine.analyze_theme(theme_id)

    # Slope should be positive
    assert analysis['trend_score'] > 0
    assert analysis['trajectory_label'] in ['increasing', 'stable', 'emerging']

def test_leverage_lift_math(test_user, freeze_time):
    user_id = test_user['id']
    engine = LeverageEngine(user_id)

    base_time = datetime(2026, 1, 1)
    freeze_time.set_time(base_time)

    t_a = db.create_theme(user_id, [0.1]*1536, "A", base_time.isoformat(), base_time.isoformat())
    t_b = db.create_theme(user_id, [0.2]*1536, "B", base_time.isoformat(), base_time.isoformat())

    # Scenario: A strictly precedes B by 2 days, 5 times.
    # P(B|A) should be 1.0 (5/5)
    # P(A|B) should be 0.0 (0/5)
    # Lift = 1.0
    for i in range(5):
        time_a = base_time + timedelta(days=i*10)
        time_b = time_a + timedelta(days=2)

        db.add_theme_occurrence(t_a, 'reflection', 200+i, "a", 0.9, time_a.isoformat())
        db.update_theme_stats(t_a, time_a.isoformat())

        db.add_theme_occurrence(t_b, 'reflection', 300+i, "b", 0.9, time_b.isoformat())
        db.update_theme_stats(t_b, time_b.isoformat())

    # Move to 'now'
    freeze_time.set_time(base_time + timedelta(days=50))

    result = engine.analyze_pair('theme', t_a, 'theme', t_b)

    assert result['directional_lift'] == 1.0
    assert result['influence_score'] == 1.0

def test_engine_empty_state_grace(test_user):
    engine = TrajectoryEngine(test_user['id'])
    # Theme with no occurrences
    t_id = db.create_theme(test_user['id'], [0.1]*1536, "Empty", datetime.now().isoformat(), datetime.now().isoformat())

    # Should not crash, should return insufficient data
    analysis = engine.analyze_theme(t_id)
    assert analysis['trajectory_label'] == "insufficient data"


def test_an_unchanged_rhythm_is_not_a_fading_one():
    """One entry every eight days, for sixty days: nothing about it changed.

    Seven-day bins sampling an eight-day rhythm leave a gap that belongs to the
    bin width rather than to the writing, and the classifier used to fall
    through to that slope exactly when the comparison it shows the owner — the
    last 14 days against the 60 before — was flat. The series scored -0.056
    against a 0.05 threshold and was reported as fading.
    """
    from datetime import UTC, datetime, timedelta

    from agent.trajectory import TrajectoryEngine

    engine = TrajectoryEngine(1)
    now = datetime.now(UTC)
    occurrences = [{"occurred_at": now - timedelta(days=d), "source_type": "reflection"}
                   for d in range(0, 60, 8)]

    slope = engine._calculate_trend_slope(occurrences)

    assert engine._classify_trajectory(len(occurrences), 0.0, slope, occurrences) == "stable"


def test_a_real_fall_in_frequency_is_still_reported():
    """The guard above must not be a licence to call everything stable."""
    from datetime import UTC, datetime, timedelta

    from agent.trajectory import TrajectoryEngine

    engine = TrajectoryEngine(1)
    now = datetime.now(UTC)
    occurrences = [{"occurred_at": now - timedelta(days=d), "source_type": "reflection"}
                   for d in (40, 41, 42, 43, 44, 45, 46, 47, 50, 55)]

    label = engine._classify_trajectory(len(occurrences), -0.8,
                                        engine._calculate_trend_slope(occurrences), occurrences)
    assert label == "fading"


def test_an_empty_pair_of_windows_is_not_a_steady_rhythm():
    """No occurrences in the recent window and none in the baseline is not a
    rate that did not change. Dropping the slope tiebreak would otherwise have
    turned silence into "stable"; resolution is the engine that speaks about
    writing that has gone quiet."""
    from datetime import UTC, datetime, timedelta

    from agent.trajectory import TrajectoryEngine

    engine = TrajectoryEngine(1)
    now = datetime.now(UTC)
    old = [{"occurred_at": now - timedelta(days=d), "source_type": "reflection"}
           for d in (300, 320, 340, 360)]

    assert engine._classify_trajectory(len(old), 0.0, 0.0, old) == "insufficient data"

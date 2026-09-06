
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
        db.add_theme_occurrence(theme_id, 'journal_entry', 100+i, "snippet", 0.9, occ_time.isoformat())
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

        db.add_theme_occurrence(t_a, 'journal_entry', 200+i, "a", 0.9, time_a.isoformat())
        db.update_theme_stats(t_a, time_a.isoformat())

        db.add_theme_occurrence(t_b, 'journal_entry', 300+i, "b", 0.9, time_b.isoformat())
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

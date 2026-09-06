
import pytest

from agent.conflict import ConflictSuppressionEngine


@pytest.fixture
def engine():
    return ConflictSuppressionEngine()

def test_conflict_higher_confidence_wins(engine):
    # Scenario: Trajectory (Increasing, High) vs Resolution (Dissipated, Medium)
    insights = [
        {
            "pattern_type": "theme",
            "pattern_id": 1,
            "engine_name": "trajectory",
            "trajectory_label": "increasing",
            "confidence_level": "high"
        },
        {
            "pattern_type": "theme",
            "pattern_id": 1,
            "engine_name": "resolution",
            "resolution_label": "dissipated",
            "confidence_level": "medium"
        }
    ]

    result = engine.suppress(insights)

    assert len(result['visible']) == 1
    assert result['visible'][0]['engine_name'] == 'trajectory'
    assert len(result['suppressed']) == 1
    assert result['suppressed'][0]['winner_engine'] == 'trajectory'

def test_conflict_priority_tiebreak(engine):
    # Scenario: Resolution (Dissipated, High) vs Trajectory (Increasing, High)
    # Both High confidence. Resolution has higher priority in constants.
    insights = [
        {
            "pattern_type": "theme",
            "pattern_id": 1,
            "engine_name": "trajectory",
            "trajectory_label": "increasing",
            "confidence_level": "high"
        },
        {
            "pattern_type": "theme",
            "pattern_id": 1,
            "engine_name": "resolution",
            "resolution_label": "dissipated",
            "confidence_level": "high"
        }
    ]

    result = engine.suppress(insights)

    assert len(result['visible']) == 1
    assert result['visible'][0]['engine_name'] == 'resolution'
    assert result['suppressed'][0]['winner_engine'] == 'resolution'

def test_coexistence_allowed(engine):
    # Scenario: Trajectory (Stable) and Leverage (High)
    # No conflict rule exists for this pair.
    insights = [
        {
            "pattern_type": "theme",
            "pattern_id": 1,
            "engine_name": "trajectory",
            "trajectory_label": "stable",
            "confidence_level": "high"
        },
        {
            "pattern_type": "theme",
            "pattern_id": 1,
            "engine_name": "leverage",
            "label": "high",
            "confidence_level": "high"
        }
    ]

    result = engine.suppress(insights)
    assert len(result['visible']) == 2
    assert len(result['suppressed']) == 0

def test_confidence_floor_ignored(engine):
    # Scenario: Conflict between Medium and Low
    # Low confidence insights should not trigger suppression logic
    # (they are filtered by the core gatekeeper usually, but the engine
    # should still handle it by original design)
    insights = [
        {
            "pattern_type": "theme",
            "pattern_id": 1,
            "engine_name": "trajectory",
            "trajectory_label": "increasing",
            "confidence_level": "medium"
        },
        {
            "pattern_type": "theme",
            "pattern_id": 1,
            "engine_name": "resolution",
            "resolution_label": "dissipated",
            "confidence_level": "low"
        }
    ]

    result = engine.suppress(insights)
    # Both should remain because Low confidence insights are ignored by Conflict Logic
    # (Wait, my implementation says: if < min_conf, they don't participate in resolution
    # but stay in 'resolved' list. This is correct as they are noise anyway.)
    assert len(result['visible']) == 2
    assert len(result['suppressed']) == 0

def test_unordered_rule_matching(engine):
    # Swap order of inputs to verify set equality works
    ins_a = {
        "pattern_type": "theme",
        "pattern_id": 1,
        "engine_name": "resolution",
        "resolution_label": "dissipated",
        "confidence_level": "high"
    }
    ins_b = {
        "pattern_type": "theme",
        "pattern_id": 1,
        "engine_name": "trajectory",
        "trajectory_label": "increasing",
        "confidence_level": "medium"
    }

    res1 = engine.suppress([ins_a, ins_b])
    res2 = engine.suppress([ins_b, ins_a])

    assert res1['visible'] == res2['visible']
    assert res1['suppressed'][0]['insight']['engine_name'] == 'trajectory'

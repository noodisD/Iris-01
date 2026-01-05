
import pytest
from datetime import datetime, timedelta
from agent.conflict import ConflictSuppressionEngine
from agent.confidence import ConfidenceEngine

def test_conflict_priority_and_confidence():
    engine = ConflictSuppressionEngine()
    
    # 1. Tie-break by Confidence: High wins over Medium
    insights = [
        {
            "engine_name": "trajectory", "pattern_type": "theme", "pattern_id": 1,
            "trajectory_label": "increasing", "confidence_level": "high"
        },
        {
            "engine_name": "resolution", "pattern_type": "theme", "pattern_id": 1,
            "resolution_label": "dissipated", "confidence_level": "medium"
        }
    ]
    res = engine.suppress(insights)
    assert len(res['visible']) == 1
    assert res['visible'][0]['engine_name'] == 'trajectory'

    # 2. Tie-break by Priority: Resolution (index 4) wins over Trajectory (index 3)
    # Both High
    insights_tie = [
        {
            "engine_name": "trajectory", "pattern_type": "theme", "pattern_id": 2,
            "trajectory_label": "increasing", "confidence_level": "high"
        },
        {
            "engine_name": "resolution", "pattern_type": "theme", "pattern_id": 2,
            "resolution_label": "dissipated", "confidence_level": "high"
        }
    ]
    res_tie = engine.suppress(insights_tie)
    assert len(res_tie['visible']) == 1
    assert res_tie['visible'][0]['engine_name'] == 'resolution'

def test_confidence_consistency_collapse():
    engine = ConfidenceEngine()
    now = datetime.now()
    timestamps = [now - timedelta(days=i) for i in range(10)]
    
    # Perfect consistency (10/10)
    res_high = engine.compute_confidence('theme', 1, timestamps, ['inc']*10)
    assert res_high['confidence_level'] == 'high'
    
    # Total collapse (5/10)
    res_low = engine.compute_confidence('theme', 1, timestamps, ['inc']*5 + ['dec']*5)
    assert res_low['confidence_level'] in ['medium', 'low']
    assert res_low['consistency_score'] == 0.5

def test_directionless_confidence_normalization():
    engine = ConfidenceEngine()
    now = datetime.now()
    timestamps = [now - timedelta(days=i) for i in range(10)]
    
    # No directions (Persistence theme)
    # Weights should re-normalize to split between sufficiency and recency
    result = engine.compute_confidence('theme', 1, timestamps, directions=None)
    
    assert result['confidence_level'] == 'high'
    assert result['consistency_score'] == 0.0
    assert result['confidence_score'] > 0.7 # High score because sufficiency and recency are strong

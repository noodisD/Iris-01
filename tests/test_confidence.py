
import pytest
from datetime import datetime, timedelta
from agent.confidence import ConfidenceEngine

@pytest.fixture
def conf_engine():
    return ConfidenceEngine()

def test_high_data_high_consistency(conf_engine):
    # 10 data points, all same direction, recent
    now = datetime.now()
    timestamps = [now - timedelta(days=i) for i in range(10)]
    directions = ['increase'] * 10
    
    result = conf_engine.compute_confidence('theme', 1, timestamps, directions)
    
    assert result['confidence_level'] == 'high'
    assert result['consistency_score'] == 1.0
    assert result['confidence_score'] > 0.8

def test_consistency_collapse(conf_engine):
    # High data (10 points) but split evenly (5 increase, 5 decrease)
    now = datetime.now()
    timestamps = [now - timedelta(days=i) for i in range(10)]
    directions = ['increase'] * 5 + ['decrease'] * 5
    
    result = conf_engine.compute_confidence('theme', 1, timestamps, directions)
    
    # Should not be 'high' despite volume, because signal is collapsed
    assert result['confidence_level'] in ['medium', 'low']
    assert result['consistency_score'] == 0.5

def test_directionless_normalization(conf_engine):
    # No directions provided (e.g. raw theme presence)
    now = datetime.now()
    timestamps = [now - timedelta(days=i) for i in range(5)]
    
    result = conf_engine.compute_confidence('theme', 1, timestamps, directions=None)
    
    # Should still compute a score and label
    assert result['confidence_level'] == 'medium'
    assert result['consistency_score'] == 0.0
    # Weighted score should still be high because w_s and w_r are re-normalized
    assert result['confidence_score'] > 0.5

def test_old_data_decay(conf_engine):
    # High volume but very old (60 days since last)
    now = datetime.now()
    timestamps = [now - timedelta(days=60+i) for i in range(10)]
    
    result = conf_engine.compute_confidence('theme', 1, timestamps)
    
    # Recency override should force it to low
    assert result['confidence_level'] == 'low'
    assert result['recency_score'] < 0.2

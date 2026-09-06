
from datetime import datetime, timedelta

import pytest

from agent.prioritization import InsightPrioritizationEngine


@pytest.fixture
def engine(test_user):
    return InsightPrioritizationEngine(test_user['id'])

def test_prioritization_determinism(engine):
    # Identical inputs must yield identical ranks
    insights = [
        {
            "engine_name": "trajectory",
            "pattern_type": "theme",
            "pattern_id": 1,
            "trajectory_label": "increasing",
            "confidence": "high",
            "computed_at": datetime.now()
        },
        {
            "engine_name": "resolution",
            "pattern_type": "theme",
            "pattern_id": 2,
            "resolution_label": "dissipated",
            "confidence": "high",
            "computed_at": datetime.now()
        }
    ]

    res1 = engine.rank_insights(list(insights))
    res2 = engine.rank_insights(list(insights))

    assert [i['pattern_id'] for i in res1] == [i['pattern_id'] for i in res2]

def test_confidence_dominance(engine):
    # High confidence (but lower magnitude) should beat Medium confidence (high magnitude)
    now = datetime.now()
    insights = [
        {
            "engine_name": "trajectory",
            "pattern_type": "theme",
            "pattern_id": 1,
            "trend_score": 0.2, # Low magnitude
            "confidence": "high",
            "computed_at": now
        },
        {
            "engine_name": "trajectory",
            "pattern_type": "theme",
            "pattern_id": 2,
            "trend_score": 0.9, # High magnitude
            "confidence": "medium",
            "computed_at": now
        }
    ]

    ranked = engine.rank_insights(insights)

    assert ranked[0]['pattern_id'] == 1
    assert ranked[0]['confidence'].lower() == 'high'

def test_diversity_rule(engine):
    # One slot per Pattern ID. Highest score wins.
    now = datetime.now()
    insights = [
        {
            "engine_name": "trajectory", # Score will be lower (base weight 0.7)
            "pattern_type": "theme",
            "pattern_id": 1,
            "confidence": "high",
            "computed_at": now
        },
        {
            "engine_name": "resolution", # Score will be higher (base weight 1.0)
            "pattern_type": "theme",
            "pattern_id": 1,
            "confidence": "high",
            "computed_at": now
        }
    ]

    ranked = engine.rank_insights(insights)

    assert len(ranked) == 1
    assert ranked[0]['engine_name'] == 'resolution'

def test_recency_impact(engine):
    # Recent beats old
    now = datetime.now()
    old = now - timedelta(days=40)

    insights = [
        {
            "engine_name": "trajectory",
            "pattern_type": "theme",
            "pattern_id": 1,
            "confidence": "high",
            "computed_at": old
        },
        {
            "engine_name": "trajectory",
            "pattern_type": "theme",
            "pattern_id": 2,
            "confidence": "high",
            "computed_at": now
        }
    ]

    ranked = engine.rank_insights(insights)
    assert ranked[0]['pattern_id'] == 2

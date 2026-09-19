
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

    res1 = engine.rank(list(insights))
    res2 = engine.rank(list(insights))

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

    ranked = engine.rank(insights)

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

    # One slot per pattern is the prompt's rule, applied when selecting; the
    # ranking itself keeps both, because the Insights screen shows both.
    assert len(engine.rank(list(insights))) == 2
    ranked = engine.select(engine.rank(insights), max_items=5)

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

    ranked = engine.rank(insights)
    assert ranked[0]['pattern_id'] == 2


def test_the_owners_budget_is_the_only_cut(engine):
    """The ranker stopped at five before the caller's own budget was applied, so
    Settings could be set to 10 and return 5 with no reason given."""
    insights = [{"engine_name": "trajectory", "pattern_type": "theme", "pattern_id": i,
                 "pattern_key": str(i), "trajectory_label": "increasing",
                 "confidence_level": "medium"} for i in range(1, 11)]

    assert len(engine.rank(list(insights))) == 10
    assert len(engine.select(engine.rank(insights), max_items=10)) == 10


def test_a_pair_is_its_own_pattern_when_selecting(engine):
    """A tension between themes 1 and 2 used to share theme 1's slot, so it
    could push a finding about theme 1 out of the prompt, or be pushed out."""
    insights = [
        {"engine_name": "trajectory", "pattern_type": "theme", "pattern_id": 1,
         "pattern_key": "1", "trajectory_label": "increasing", "confidence_level": "medium"},
        {"engine_name": "tension", "pattern_type": "theme", "pattern_id": 1,
         "pattern_key": "1-2", "tension_label": "persistent", "confidence_level": "medium"},
    ]
    assert len(engine.select(engine.rank(insights), max_items=5)) == 2


def test_the_two_year_view_loses_every_tie(engine):
    """ENGINE_PRIORITY said lifelong came last so it would yield — and a higher
    index wins, so it won every tie it was documented to lose. Both consumers of
    the order (ranking and conflict suppression) read it the same way."""
    from agent.conflict import ConflictSuppressionEngine
    from agent.constants import ENGINE_BASE_WEIGHTS, ENGINE_PRIORITY

    assert ENGINE_PRIORITY[0] == "lifelong"
    assert min(engine.engine_tiebreak_prio, key=engine.engine_tiebreak_prio.get) == "lifelong"
    assert min(ConflictSuppressionEngine().priority,
               key=ConflictSuppressionEngine().priority.get) == "lifelong"
    assert ENGINE_BASE_WEIGHTS["lifelong"] == min(ENGINE_BASE_WEIGHTS.values())


def test_dropping_novelty_changed_no_order(engine):
    """Novelty was 15% of the score and always 0.5 — no engine set it. The
    weights without it are the old ones scaled by 1/0.85, so the order is the
    old formula's, except where two scores sit within the rounding the ranker
    sorts on and the tie-breakers decide."""
    now = datetime.now()
    engines = ["trajectory", "resolution", "tension", "leverage", "decision_impact", "lifelong"]
    insights = [
        {"engine_name": engines[n % 6], "pattern_type": "theme", "pattern_id": n + 1,
         "confidence": ("high", "medium")[n % 2], "computed_at": now - timedelta(days=(n * 7) % 60),
         "influence_score": (n * 37 % 100) / 100}
        for n in range(24)
    ]

    def old_score(i):
        b = engine._calculate_score(i)
        return (0.35 * b["conf"] + 0.20 * b["recency"] + 0.20 * b["magnitude"]
                + 0.15 * 0.5 + 0.10 * b["engine"])

    ranked = engine.rank([dict(i) for i in insights])
    for above, below in zip(ranked, ranked[1:]):
        assert old_score(above) > old_score(below) - 0.001, (above["pattern_id"], below["pattern_id"])


import pytest
from datetime import datetime, timedelta
from agent.database import db
from agent.leverage import LeverageEngine
from agent.constants import LEVERAGE_WINDOW_DAYS, LEVERAGE_TIME_LAG_DAYS

@pytest.fixture
def leverage_engine(test_user):
    return LeverageEngine(test_user['id'])

def test_asymmetric_influence_detected(test_user, leverage_engine):
    # Scenario: Theme A frequently precedes Theme B by 2 days
    now = datetime.now()
    
    theme_a_id = db.create_theme(
        user_id=test_user['id'],
        centroid_embedding=[0.1] * 1536,
        summary="Driver Theme A",
        first_seen_at=(now - timedelta(days=60)).isoformat(),
        last_seen_at=now.isoformat()
    )
    
    theme_b_id = db.create_theme(
        user_id=test_user['id'],
        centroid_embedding=[0.2] * 1536,
        summary="Target Theme B",
        first_seen_at=(now - timedelta(days=60)).isoformat(),
        last_seen_at=now.isoformat()
    )
    
    # Add 5 pairs where A happens, then B happens 2 days later
    for i in range(5):
        a_date = now - timedelta(days=30 + i*5)
        b_date = a_date + timedelta(days=2)
        
        # Add occurrences and update stats
        db.add_theme_occurrence(theme_a_id, 'journal_entry', 1000+i, "occ a", 0.9, a_date.isoformat())
        db.update_theme_stats(theme_a_id, a_date.isoformat())
        
        db.add_theme_occurrence(theme_b_id, 'journal_entry', 2000+i, "occ b", 0.9, b_date.isoformat())
        db.update_theme_stats(theme_b_id, b_date.isoformat())
        
    # Analyze
    result = leverage_engine.analyze_pair('theme', theme_a_id, 'theme', theme_b_id)
    
    assert result is not None
    assert result['directional_lift'] > 0.5
    assert result['influence_score'] > 0.5
    assert result['confidence_level'] in ['high', 'medium']

def test_symmetric_patterns_rejected(test_user, leverage_engine):
    # Scenario: Theme A and Theme B always occur on the same day
    now = datetime.now()
    
    theme_a_id = db.create_theme(
        user_id=test_user['id'],
        centroid_embedding=[0.3] * 1536,
        summary="Symmetric A",
        first_seen_at=(now - timedelta(days=60)).isoformat(),
        last_seen_at=now.isoformat()
    )
    
    theme_b_id = db.create_theme(
        user_id=test_user['id'],
        centroid_embedding=[0.4] * 1536,
        summary="Symmetric B",
        first_seen_at=(now - timedelta(days=60)).isoformat(),
        last_seen_at=now.isoformat()
    )
    
    for i in range(5):
        occ_date = now - timedelta(days=30 + i*5)
        
        db.add_theme_occurrence(theme_a_id, 'journal_entry', 3000+i, "occ a", 0.9, occ_date.isoformat())
        db.update_theme_stats(theme_a_id, occ_date.isoformat())
        
        db.add_theme_occurrence(theme_b_id, 'journal_entry', 3000+i, "occ b", 0.9, occ_date.isoformat())
        db.update_theme_stats(theme_b_id, occ_date.isoformat())
        
    result = leverage_engine.analyze_pair('theme', theme_a_id, 'theme', theme_b_id)
    
    # Simultaneous counts are excluded from lift calculation in my logic
    # P(B|A) = Forward / Total = 0 / 5 = 0
    # P(A|B) = Backward / Total = 0 / 5 = 0
    # Lift = 0
    assert result is not None
    assert result['directional_lift'] == 0
    assert result['influence_score'] == 0

def test_noise_filtering_low_counts(test_user, leverage_engine):
    now = datetime.now()
    theme_a_id = db.create_theme(test_user['id'], [0.5]*1536, "Noise A", now.isoformat(), now.isoformat())
    theme_b_id = db.create_theme(test_user['id'], [0.6]*1536, "Noise B", now.isoformat(), now.isoformat())
    
    # Only 2 occurrences (min is 5)
    for i in range(2):
        db.add_theme_occurrence(theme_a_id, 'journal_entry', 4000+i, "a", 0.9, now.isoformat())
        db.update_theme_stats(theme_a_id, now.isoformat())
        
    result = leverage_engine.analyze_pair('theme', theme_a_id, 'theme', theme_b_id)
    assert result is None

def test_cache_invalidation(test_user, leverage_engine):
    now = datetime.now()
    theme_a_id = db.create_theme(test_user['id'], [0.7]*1536, "Source", now.isoformat(), now.isoformat())
    theme_b_id = db.create_theme(test_user['id'], [0.8]*1536, "Target", now.isoformat(), now.isoformat())
    
    # 1. Setup leverage
    for i in range(5):
        a_date = now - timedelta(days=30 + i*5)
        b_date = a_date + timedelta(days=2)
        db.add_theme_occurrence(theme_a_id, 'journal_entry', 5000+i, "a", 0.9, a_date.isoformat())
        db.update_theme_stats(theme_a_id, a_date.isoformat())
        db.add_theme_occurrence(theme_b_id, 'journal_entry', 6000+i, "b", 0.9, b_date.isoformat())
        db.update_theme_stats(theme_b_id, b_date.isoformat())
        
    # 2. Analyze (populates cache)
    leverage_engine.analyze_pair('theme', theme_a_id, 'theme', theme_b_id)
    targets = db.get_leverage_targets('theme', theme_a_id)
    assert len(targets) > 0
    
    # 3. Add NEW occurrence (invalidates cache)
    db.add_theme_occurrence(theme_a_id, 'journal_entry', 7000, "new", 0.9, now.isoformat())
    # Note: add_theme_occurrence has the invalidate call
    
    # 4. Check cache is NULL
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT last_computed_at FROM pattern_leverage WHERE source_id = %s", (theme_a_id,))
        last_computed = cur.fetchone()[0]
        assert last_computed is None

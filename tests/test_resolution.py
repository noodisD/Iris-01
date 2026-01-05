
import pytest
from datetime import datetime, timedelta
from agent.database import db
from agent.resolution import ResolutionEngine
from agent.constants import RESOLUTION_RECENT_DAYS, RESOLUTION_BASELINE_DAYS

@pytest.fixture
def resolution_engine(test_user):
    return ResolutionEngine(test_user['id'])

def test_theme_dissipates_after_silence(test_user, resolution_engine):
    # 1. Create a theme
    now = datetime.now()
    theme_id = db.create_theme(
        user_id=test_user['id'],
        centroid_embedding=[0.1] * 1536,
        summary="Dissipated Theme",
        first_seen_at=(now - timedelta(days=60)).isoformat(),
        last_seen_at=(now - timedelta(days=30)).isoformat()
    )
    
    # 2. Add occurrences in the baseline window (21-111 days ago based on constants)
    # 3 occurrences to reach RESOLUTION_MIN_DATA_POINTS
    for i in range(3):
        db.add_theme_occurrence(
            theme_id=theme_id,
            source_type='journal_entry',
            source_id=100+i,
            snippet="past occurrence",
            similarity_score=0.9,
            occurred_at=(now - timedelta(days=40 + i)).isoformat()
        )
        
    # 3. Analyze (Recent count will be 0 as occurrences are > 21 days ago)
    analysis = resolution_engine.analyze_theme(theme_id, force_recompute=True)
    
    assert analysis['resolution_label'] == 'dissipated'
    assert analysis['recent_count'] == 0
    assert analysis['past_count'] >= 3
    assert analysis['confidence_level'] in ['high', 'medium']

def test_theme_reappears_after_gap(test_user, resolution_engine):
    # 1. Create a theme
    now = datetime.now()
    theme_id = db.create_theme(
        user_id=test_user['id'],
        centroid_embedding=[0.2] * 1536,
        summary="Reappearing Theme",
        first_seen_at=(now - timedelta(days=100)).isoformat(),
        last_seen_at=now.isoformat()
    )
    
    # 2. Add occurrences in baseline
    for i in range(3):
        db.add_theme_occurrence(
            theme_id=theme_id,
            source_type='journal_entry',
            source_id=200+i,
            snippet="past occurrence",
            similarity_score=0.9,
            occurred_at=(now - timedelta(days=60 + i)).isoformat()
        )
        
    # 3. Add occurrence in recent (within 21 days)
    db.add_theme_occurrence(
        theme_id=theme_id,
        source_type='journal_entry',
        source_id=210,
        snippet="recent occurrence",
        similarity_score=0.9,
        occurred_at=(now - timedelta(days=1)).isoformat()
    )
    
    # 4. Analyze
    analysis = resolution_engine.analyze_theme(theme_id, force_recompute=True)
    
    assert analysis['resolution_label'] == 'reappearing'
    assert analysis['recent_count'] == 1
    assert analysis['past_count'] >= 3

def test_stabilized_pattern(test_user, resolution_engine):
    # Baseline: 90 days. Recent: 21 days.
    # Past rate: 9/90 = 0.1 per day
    # Recent rate: 2/21 = 0.095 per day
    # Attenuation = 1 - (0.095 / 0.1) = 0.05 (exactly epsilon)
    
    now = datetime.now()
    theme_id = db.create_theme(
        user_id=test_user['id'],
        centroid_embedding=[0.3] * 1536,
        summary="Stabilized Theme",
        first_seen_at=(now - timedelta(days=100)).isoformat(),
        last_seen_at=now.isoformat()
    )
    
    # Baseline (21 to 111 days ago)
    for i in range(9):
        db.add_theme_occurrence(
            theme_id=theme_id,
            source_type='journal_entry',
            source_id=300+i,
            snippet="past",
            similarity_score=0.9,
            occurred_at=(now - timedelta(days=40+i)).isoformat()
        )
        
    # Recent (last 21 days)
    for i in range(2):
        db.add_theme_occurrence(
            theme_id=theme_id,
            source_type='journal_entry',
            source_id=400+i,
            snippet="recent",
            similarity_score=0.9,
            occurred_at=(now - timedelta(days=5+i)).isoformat()
        )
        
    analysis = resolution_engine.analyze_theme(theme_id, force_recompute=True)
    assert analysis['resolution_label'] == 'stabilized'

def test_false_dissipation_low_confidence(test_user, resolution_engine):
    now = datetime.now()
    theme_id = db.create_theme(
        user_id=test_user['id'],
        centroid_embedding=[0.4] * 1536,
        summary="Low Confidence",
        first_seen_at=(now - timedelta(days=60)).isoformat(),
        last_seen_at=(now - timedelta(days=40)).isoformat()
    )
    
    # Only 1 occurrence (below RESOLUTION_MIN_DATA_POINTS=3)
    db.add_theme_occurrence(
        theme_id=theme_id,
        source_type='journal_entry',
        source_id=500,
        snippet="past",
        similarity_score=0.9,
        occurred_at=(now - timedelta(days=40)).isoformat()
    )
    
    analysis = resolution_engine.analyze_theme(theme_id, force_recompute=True)
    assert analysis['confidence_level'] == 'low'

def test_cache_invalidation(test_user, resolution_engine):
    now = datetime.now()
    theme_id = db.create_theme(
        user_id=test_user['id'],
        centroid_embedding=[0.5] * 1536,
        summary="Cache Test",
        first_seen_at=(now - timedelta(days=60)).isoformat(),
        last_seen_at=(now - timedelta(days=30)).isoformat()
    )
    
    # 1. Add baseline data
    for i in range(3):
        db.add_theme_occurrence(
            theme_id=theme_id,
            source_type='journal_entry',
            source_id=600+i,
            snippet="past",
            similarity_score=0.9,
            occurred_at=(now - timedelta(days=50 + i)).isoformat()
        )
    
    # 2. Compute and cache
    analysis1 = resolution_engine.analyze_theme(theme_id)
    assert analysis1['resolution_label'] == 'dissipated'
    
    # Verify it is cached in DB
    cached = db.get_resolution('theme', theme_id)
    assert cached is not None
    assert cached['last_computed_at'] is not None
    
    # 3. Add a NEW occurrence (should invalidate cache)
    db.add_theme_occurrence(
        theme_id=theme_id,
        source_type='journal_entry',
        source_id=700,
        snippet="new",
        similarity_score=0.9,
        occurred_at=now.isoformat()
    )
    
    # 4. Verify cache is invalid
    cached_invalid = db.get_resolution('theme', theme_id)
    assert cached_invalid['last_computed_at'] is None
    
    # 5. Re-analyze (should compute as reappearing)
    analysis2 = resolution_engine.analyze_theme(theme_id)
    assert analysis2['resolution_label'] == 'reappearing'

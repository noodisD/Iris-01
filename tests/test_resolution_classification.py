"""
TDD test to verify resolution classification works correctly.

Behavior to test:
- When a theme has occurrences in the past but none in the recent window (21 days),
  it should be classified as 'dissipated', not 'persisting'.
"""
import pytest
from datetime import datetime, timedelta
from agent.database import db
from agent.resolution import ResolutionEngine
from agent.constants import RESOLUTION_RECENT_DAYS, RESOLUTION_MIN_DATA_POINTS


def test_theme_dissipated_when_no_recent_activity(test_user):
    """
    GIVEN: A theme with past occurrences but none in the recent 21-day window
    WHEN:  ResolutionEngine analyzes it
    THEN:  It should classify as 'dissipated', not 'persisting'
    """
    user_id = test_user['id']
    now = datetime.now()
    
    # Create a theme
    theme_id = db.create_theme(
        user_id, 
        [0.1]*1536, 
        "Test Dissipated Theme",
        (now - timedelta(days=60)).isoformat(),
        now.isoformat()
    )
    
    # Add occurrences only in the PAST (> 21 days ago)
    for i in range(5):  # More than RESOLUTION_MIN_DATA_POINTS
        days_ago = 30 + (i * 5)  # 30, 35, 40, 45, 50 days ago
        occ_date = now - timedelta(days=days_ago)
        entry_id = db.create_journal_entry(user_id, f"Entry {i}", {})
        db.add_theme_occurrence(
            theme_id, 
            'journal_entry', 
            entry_id, 
            "snippet",
            0.95,
            occ_date.isoformat()
        )
    
    # Analyze the theme
    engine = ResolutionEngine(user_id)
    result = engine.analyze_theme(theme_id, force_recompute=True)
    
    # Verify the classification
    print(f"\nResolution Analysis Results:")
    print(f"  Resolution Label: {result['resolution_label']}")
    print(f"  Recent Count: {result['recent_count']} (window: {RESOLUTION_RECENT_DAYS} days)")
    print(f"  Past Count: {result['past_count']} (min required: {RESOLUTION_MIN_DATA_POINTS})")
    print(f"  Attenuation Score: {result['attenuation_score']}")
    print(f"  Confidence: {result['confidence_level']}")
    
    # Verify preconditions
    assert result['recent_count'] == 0, \
        f"Expected 0 recent occurrences, got {result['recent_count']}"
    assert result['past_count'] >= RESOLUTION_MIN_DATA_POINTS, \
        f"Expected past_count >= {RESOLUTION_MIN_DATA_POINTS}, got {result['past_count']}"
    
    # The main assertion
    assert result['resolution_label'] == 'dissipated', \
        f"Expected resolution_label='dissipated' but got '{result['resolution_label']}'. " \
        f"Attenuation: {result['attenuation_score']:.3f}"

"""
Test to verify resolution caching works correctly when manually forced.
"""
from datetime import datetime, timedelta

from agent.database import db
from agent.resolution import ResolutionEngine


def test_resolution_cache_uses_forced_value(test_user):
    """
    GIVEN: A theme with an analysis result cached as 'persisting'
    WHEN: The resolution is manually updated to 'dissipated'
    THEN: The cache should return the forced 'dissipated' value
    """
    user_id = test_user['id']
    now = datetime.now()

    # Create theme
    theme_id = db.create_theme(
        user_id,
        [0.1]*1536,
        "Test Theme",
        (now - timedelta(days=60)).isoformat(),
        now.isoformat()
    )

    # Add some past occurrences
    for i in range(5):
        days_ago = 30 + (i * 5)
        entry_id = db.create_journal_entry(user_id, f"Entry {i}", {})
        db.add_theme_occurrence(
            theme_id,
            'journal_entry',
            entry_id,
            "snippet",
            0.95,
            (now - timedelta(days=days_ago)).isoformat()
        )

    # First analysis (should get 'dissipated')
    engine1 = ResolutionEngine(user_id)
    result1 = engine1.analyze_theme(theme_id, force_recompute=True)
    print(f"\nFirst analysis: {result1['resolution_label']}")
    assert result1['resolution_label'] == 'dissipated'

    # Manually force to 'persisting' (opposite of what it should be)
    db.create_or_update_resolution(
        'theme', theme_id,
        resolution_label='persisting',  # Force wrong value
        attenuation_score=0.0,
        confidence_level='low',
        recent_count=10,  # Claim there are recent occurrences
        past_count=10
    )
    print("Forced 'persisting' in cache")

    # Second analysis (should use cache and return 'persisting')
    engine2 = ResolutionEngine(user_id)
    result2 = engine2.analyze_theme(theme_id, force_recompute=False)
    print(f"Second analysis (cached): {result2['resolution_label']}")
    assert result2['resolution_label'] == 'persisting', "Cache should be used"

    # Now force back to 'dissipated'
    db.create_or_update_resolution(
        'theme', theme_id,
        resolution_label='dissipated',  # Restore correct value
        attenuation_score=1.0,
        confidence_level='high',
        recent_count=0,
        past_count=20
    )
    print("Forced back to 'dissipated' in cache")

    # Third analysis (should use cache and return 'dissipated')
    engine3 = ResolutionEngine(user_id)
    result3 = engine3.analyze_theme(theme_id, force_recompute=False)
    print(f"Third analysis (cached): {result3['resolution_label']}")
    assert result3['resolution_label'] == 'dissipated', "Updated cache should be used"

"""
Test that manually overridden resolutions in the DB are properly cached.
"""
from datetime import datetime, timedelta

from agent.database import db
from agent.resolution import ResolutionEngine


def test_manual_resolution_override(test_user):
    """
    Verify that when a resolution is manually set in the DB,
    subsequent calls to ResolutionEngine return the cached value.
    """
    user_id = test_user['id']
    now = datetime.now()

    # Create a theme with occurrences in the past (> 21 days ago)
    theme = db.create_theme(
        user_id,
        [0.1] * 1536,
        "Test Theme",
        (now - timedelta(days=90)).isoformat(),
        now.isoformat()
    )

    # Add occurrences 30-50 days ago
    for i in range(5):
        days_ago = 30 + (i * 5)
        d = now - timedelta(days=days_ago)
        entry = db.create_journal_entry(user_id, f"Entry {i}", {})
        db.add_theme_occurrence(theme, 'journal_entry', entry, "test", 0.95, d.isoformat())
        db.update_theme_stats(theme, d.isoformat())

    # Manually override the resolution to 'dissipated'
    db.create_or_update_resolution(
        pattern_type='theme',
        pattern_id=theme,
        resolution_label='dissipated',
        attenuation_score=1.0,
        confidence_level='high',
        recent_count=0,
        past_count=10
    )

    # Now analyze - should return the cached value
    engine = ResolutionEngine(user_id)
    result = engine.analyze_theme(theme, force_recompute=False)

    print("\nDEBUG Manual Override Test:")
    print(f"  Theme ID: {theme}")
    print(f"  Result label: {result['resolution_label']}")
    print(f"  Result confidence: {result['confidence_level']}")
    print(f"  Result recent_count: {result['recent_count']}")
    print(f"  Result past_count: {result['past_count']}")

    assert result['resolution_label'] == 'dissipated', \
        f"Expected 'dissipated' but got '{result['resolution_label']}'"
    assert result['confidence_level'] == 'high'


def test_stress_theme_exact_scenario(test_user):
    """
    Replicate the exact stress theme scenario from test_final_system_stress_test.py
    """
    user_id = test_user['id']
    now = datetime.now()

    # Create stress theme exactly as the test does
    t_stress = db.create_theme(user_id, [0.1]*1536, "Work Stress", (now-timedelta(days=120)).isoformat(), now.isoformat())

    # SCENARIO A: Leverage (Stress -> Sleep)
    for i in range(6):
        d_s = now - timedelta(days=60 - (i*6))
        eid = db.create_journal_entry(user_id, f"Stress {i}", {})
        db.add_theme_occurrence(t_stress, 'journal_entry', eid, "stress", 0.95, d_s.isoformat())
        db.update_theme_stats(t_stress, d_s.isoformat())

    # SCENARIO B: Tension (Stress & Yoga co-occur)
    for i in range(7):
        d_t = now - timedelta(days=40 - i*2)
        eid = db.create_journal_entry(user_id, f"Stress & Yoga {i}", {})
        db.add_theme_occurrence(t_stress, 'journal_entry', eid, "stress", 0.95, d_t.isoformat())
        db.update_theme_stats(t_stress, d_t.isoformat())

    # SCENARIO D: Impact (Meditation -> Stress Fade)
    med_anchors = [now - timedelta(days=200), now - timedelta(days=120), now - timedelta(days=70)]
    for i, d_m in enumerate(med_anchors):
        for j in range(3):
            d_s_base = d_m - timedelta(days=5+j)
            eid_s = db.create_journal_entry(user_id, f"Stress pre-med {i}-{j}", {})
            db.add_theme_occurrence(t_stress, 'journal_entry', eid_s, "stress", 0.95, d_s_base.isoformat())
            db.update_theme_stats(t_stress, d_s_base.isoformat())

    # Get all occurrences
    occs = db.get_theme_occurrences(t_stress)
    print("\nDEBUG Stress Theme Scenario:")
    print(f"  Total occurrences: {len(occs)}")

    # Show which are in recent window (last 21 days)
    # occurred_at is TIMESTAMPTZ; drop the offset before comparing against a
    # naive 'now' rather than mixing aware and naive datetimes.
    def _naive(o):
        dt = datetime.fromisoformat(str(o['occurred_at']))
        return dt.replace(tzinfo=None) if dt.tzinfo else dt

    recent = [o for o in occs if (now - _naive(o)).days <= 21]
    baseline_start = now - timedelta(days=111)
    baseline_end = now - timedelta(days=21)
    baseline = [o for o in occs if baseline_start <= _naive(o) < baseline_end]

    print(f"  Recent (0-21 days): {len(recent)}")
    print(f"  Baseline (21-111 days): {len(baseline)}")

    # Print actual occurrences
    occ_dates = sorted([_naive(o) for o in occs], reverse=True)
    print("  Occurrence dates (days ago):")
    for occ_dt in occ_dates[:10]:  # First 10
        days_ago = (now - occ_dt).days
        print(f"    - {days_ago} days ago")

    # Now analyze naturally (without override)
    engine = ResolutionEngine(user_id)
    result = engine.analyze_theme(t_stress, force_recompute=True)

    print("\n  Natural analysis result:")
    print(f"    Label: {result['resolution_label']}")
    print(f"    Confidence: {result['confidence_level']}")
    print(f"    Recent count: {result['recent_count']}")
    print(f"    Past count: {result['past_count']}")

    # Now override and re-analyze
    db.create_or_update_resolution(
        pattern_type='theme',
        pattern_id=t_stress,
        resolution_label='dissipated',
        attenuation_score=1.0,
        confidence_level='high',
        recent_count=0,
        past_count=20
    )

    # Analyze again - should get cached value
    result2 = engine.analyze_theme(t_stress, force_recompute=False)
    print("\n  After override:")
    print(f"    Label: {result2['resolution_label']}")
    print(f"    Confidence: {result2['confidence_level']}")

    assert result2['resolution_label'] == 'dissipated'

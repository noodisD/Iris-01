"""
Debug test replicating the exact scenario from test_final_system_stress_test.py
"""
import pytest
from datetime import datetime, timedelta
from agent.database import db
from agent.resolution import ResolutionEngine
from agent.constants import RESOLUTION_RECENT_DAYS


def test_stress_theme_resolution_debug(test_user, mock_pipeline_logic):
    """Replicate test_final_system_integrated_flow's scenario for Work Stress"""
    user_id = test_user['id']
    now = datetime.now()
    
    print(f"\n=== TEST DATA CREATION ===")
    print(f"Test 'now': {now}")
    
    # Create themes exactly like the test does
    t_stress = db.create_theme(user_id, [0.1]*1536, "Work Stress", 
                               (now-timedelta(days=120)).isoformat(), 
                               now.isoformat())
    
    # SCENARIO A: Leverage (Stress -> Sleep)
    print(f"\n=== SCENARIO A: Stress Occurrences ===")
    for i in range(6):
        d_s = now - timedelta(days=60 - (i*6))
        print(f"  Entry {i}: {(datetime.now() - d_s).total_seconds() / 86400:.1f} days ago")
        eid = db.create_journal_entry(user_id, f"Stress {i}", {})
        db.add_theme_occurrence(t_stress, 'journal_entry', eid, "stress", 0.95, d_s.isoformat())
        db.update_theme_stats(t_stress, d_s.isoformat())
    
    # SCENARIO B: Tension (Stress & Yoga co-occur)
    print(f"\n=== SCENARIO B: Stress Occurrences (Tension) ===")
    for i in range(7):
        d_t = now - timedelta(days=40 - i*2)
        print(f"  Entry {i}: {(datetime.now() - d_t).total_seconds() / 86400:.1f} days ago")
        eid = db.create_journal_entry(user_id, f"Stress & Yoga {i}", {})
        db.add_theme_occurrence(t_stress, 'journal_entry', eid, "stress", 0.95, d_t.isoformat())
        db.update_theme_stats(t_stress, d_t.isoformat())
    
    # SCENARIO D: Impact (Meditation -> Stress Fade)
    print(f"\n=== SCENARIO D: Stress Occurrences (Before Meditation) ===")
    med_anchors = [now - timedelta(days=200), now - timedelta(days=120), now - timedelta(days=70)]
    for i, d_m in enumerate(med_anchors):
        for j in range(3):
            d_s_base = d_m - timedelta(days=5+j)
            days_ago = (datetime.now() - d_s_base).total_seconds() / 86400
            print(f"  Before anchor {i}: {days_ago:.1f} days ago")
            eid_s = db.create_journal_entry(user_id, f"Stress pre-med {i}-{j}", {})
            db.add_theme_occurrence(t_stress, 'journal_entry', eid_s, "stress", 0.95, d_s_base.isoformat())
            db.update_theme_stats(t_stress, d_s_base.isoformat())
    
    # Now analyze
    print(f"\n=== ANALYSIS TIME ===")
    print(f"Analysis 'now': {datetime.now()}")
    print(f"Time elapsed since data creation: {(datetime.now() - now).total_seconds():.2f} seconds")
    
    # Get all occurrences
    occs = db.get_theme_occurrences(t_stress)
    print(f"\n=== ACTUAL OCCURRENCES IN DATABASE ===")
    print(f"Total occurrences: {len(occs)}")
    
    for occ in occs:
        occ_dt = occ['occurred_at']
        if isinstance(occ_dt, str):
            occ_dt = datetime.fromisoformat(occ_dt)
        # occurred_at is TIMESTAMPTZ; compare naive-to-naive.
        if occ_dt.tzinfo:
            occ_dt = occ_dt.replace(tzinfo=None)
        days_ago = (datetime.now() - occ_dt).total_seconds() / 86400
        in_recent = days_ago <= RESOLUTION_RECENT_DAYS
        print(f"  {days_ago:.1f} days ago | Recent: {in_recent}")
    
    # Analyze
    engine = ResolutionEngine(user_id)
    result = engine.analyze_theme(t_stress, force_recompute=True)
    
    print(f"\n=== RESOLUTION ANALYSIS RESULT ===")
    print(f"Recent count: {result['recent_count']} (window: {RESOLUTION_RECENT_DAYS} days)")
    print(f"Past count: {result['past_count']}")
    print(f"Attenuation score: {result['attenuation_score']:.3f}")
    print(f"Confidence: {result['confidence_level']}")
    print(f"Resolution label: {result['resolution_label']}")
    
    # This should be 'dissipated'
    if result['resolution_label'] != 'dissipated':
        print(f"\n⚠️  PROBLEM: Expected 'dissipated' but got '{result['resolution_label']}'")

"""
Test to verify that manually-overridden resolutions survive re-analysis.
This tests the exact scenario from test_final_system_stress_test.py.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from agent.core import PersonalAICompanion
from agent.database import db, resolutions, confidence
from agent.resolution import ResolutionEngine


def test_resolution_override_survives_pipeline(test_user, monkeypatch):
    """
    Verify that a manually-set resolution survives re-analysis through the full pipeline.

    This reproduces the exact scenario from test_final_system_stress_test.py PHASE 4.
    """
    user_id = test_user['id']
    now = datetime.now()

    # Create theme and add occurrences (all > 21 days ago)
    theme = db.create_theme(user_id, [0.1]*1536, "Stress Theme",
                           (now-timedelta(days=120)).isoformat(), now.isoformat())

    # Add occurrences 28-60 days ago (13 occurrences)
    for days_ago in [28, 30, 30, 32, 34, 36, 36, 38, 40, 42, 48, 54, 60]:
        d = now - timedelta(days=days_ago)
        entry = db.create_journal_entry(user_id, f"Entry at day {days_ago}", {})
        db.add_theme_occurrence(theme, 'journal_entry', entry, "stress", 0.95, d.isoformat())
        db.update_theme_stats(theme, d.isoformat())

    # Add old occurrences (75-207 days ago)
    for days_ago in [75, 76, 77, 125, 126, 127, 205, 206, 207]:
        d = now - timedelta(days=days_ago)
        entry = db.create_journal_entry(user_id, f"Entry at day {days_ago}", {})
        db.add_theme_occurrence(theme, 'journal_entry', entry, "stress", 0.95, d.isoformat())
        db.update_theme_stats(theme, d.isoformat())

    # Step 1: Natural analysis (should return dissipated)
    print("\n=== STEP 1: Natural Analysis ===")
    engine = ResolutionEngine(user_id)
    natural = engine.analyze_theme(theme, force_recompute=True)
    print(f"Natural analysis: {natural['resolution_label']}")
    print(f"  recent_count={natural['recent_count']}, past_count={natural['past_count']}")
    assert natural['resolution_label'] == 'dissipated', \
        f"Natural analysis should return 'dissipated', got '{natural['resolution_label']}'"

    # Step 2: Manually override (simulate PHASE 4 of test)
    print("\n=== STEP 2: Manual Override ===")
    resolutions.create_or_update('theme', theme, 'dissipated', 1.0, 'high', 0, 20)
    confidence.create_or_update('resolution', theme, 'high', 0.9, 20, 100, 1.0, 0.5)
    print("Manually set resolution to 'dissipated' with high confidence")

    # Verify manual override is in DB
    cached = resolutions.get_resolution('theme', theme)
    print(f"Cached value after override: {cached['resolution_label']}")
    assert cached['resolution_label'] == 'dissipated'

    # Step 3: Re-analyze through cache (should return dissipated from cache)
    print("\n=== STEP 3: Cache Lookup ===")
    cached_result = engine.analyze_theme(theme, force_recompute=False)
    print(f"Cache lookup result: {cached_result['resolution_label']}")
    assert cached_result['resolution_label'] == 'dissipated', \
        f"Cache should return 'dissipated', got '{cached_result['resolution_label']}'"

    # Step 4: Full pipeline through companion.chat()
    print("\n=== STEP 4: Full Pipeline ===")

    # Mock the embedding function to avoid API calls
    monkeypatch.setattr("agent.pipeline.generate_embedding", lambda text, model=None: [0.1] * 1536)
    monkeypatch.setattr("agent.core.generate_embedding", lambda text, model=None: [0.1] * 1536)

    # Mock other graph operations
    monkeypatch.setattr("agent.pipeline.graph_db.add_journal_entry_node", lambda *a, **k: None)
    monkeypatch.setattr("agent.pipeline.graph_db.add_idea_node", lambda *a, **k: None)
    monkeypatch.setattr("agent.pipeline.graph_db.link_journal_to_idea", lambda *a, **k: None)

    # Mock the LLM
    companion = PersonalAICompanion(user_id=user_id)
    companion.intelligence.chat = MagicMock(return_value="OK")

    # Call chat
    companion.chat("Test message")

    # Extract the system prompt
    prompt = companion.intelligence.chat.call_args[1]['system_prompt']

    # Check that the resolution narrative is present with correct label
    print(f"Checking narrative in prompt...")
    if "Stress Theme" in prompt:
        print("✓ Theme name found in prompt")
    else:
        print("✗ Theme name NOT found in prompt")

    if "appeared frequently in the past but has not appeared recently" in prompt:
        print("✓ Dissipated narrative found!")
    elif "appeared frequently in the past but persisting recently" in prompt:
        print("✗ WRONG narrative: persisting instead of dissipated")
        print(f"\nFull prompt:\n{prompt}\n")
        raise AssertionError("Resolution narrative shows 'persisting' instead of 'dissipated'")
    else:
        print("✗ No resolution narrative found")
        print(f"\nFull prompt:\n{prompt}\n")
        raise AssertionError("No resolution narrative found in prompt")

    print("\n=== TEST PASSED ===")

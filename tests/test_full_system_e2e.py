
import pytest
import time
import logging
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from agent.core import PersonalAICompanion
from agent.database import db
from agent.persistence import PersistenceEngine
from agent.trajectory import TrajectoryEngine
from agent.tension import TensionEngine
from agent.resolution import ResolutionEngine
from agent.leverage import LeverageEngine
from agent.decision_impact import DecisionImpactEngine
from agent.confidence import ConfidenceEngine
from agent.explanation import ExplanationEngine

# Setup logging
logger = logging.getLogger("FullSystemTest")

@pytest.fixture
def mock_external_services(monkeypatch):
    import random
    def mock_embed(text, model=None):
        if "Stress" in text: return [0.1] * 1536
        if "Sleep" in text: return [0.2] * 1536
        if "Yoga" in text: return [0.3] * 1536
        if "Habit" in text: return [0.4] * 1536
        if "Spurious" in text: return [0.9] * 1536
        return [random.random() for _ in range(1536)]

    monkeypatch.setattr("agent.pipeline.generate_embedding", mock_embed)
    monkeypatch.setattr("agent.core.generate_embedding", mock_embed)
    monkeypatch.setattr("agent.pipeline.graph_db.add_journal_entry_node", lambda *a: None)
    monkeypatch.setattr("agent.pipeline.graph_db.add_idea_node", lambda *a: None)
    monkeypatch.setattr("agent.pipeline.graph_db.link_journal_to_idea", lambda *a: None)
    monkeypatch.setattr("agent.persistence.PersistenceEngine._generate_theme_summary", lambda s, e: "Simulated Theme")

def test_full_system_with_meta_controls(test_user, mock_external_services):
    """
    Final comprehensive test verifying Confidence Gate AND Conflict Suppression.
    Scenario:
    1. 'Work Stress' is robustly Increasing (Trajectory, High Conf).
    2. But we force a fake Resolution record saying it's Dissipated (Resolution, Medium Conf).
    3. Conflict Engine should suppress the fake Resolution.
    """
    user_id = test_user['id']
    now = datetime.now()
    
    logger.info("Starting System Test with Meta-Controls (Confidence & Conflict)...")
    
    # Create Theme
    t_stress = db.create_theme(user_id, [0.1]*1536, "Work Stress", (now-timedelta(days=100)).isoformat(), now.isoformat())

    # --- 1. Robust TRAJECTORY (Increasing) ---
    # 15 recent points over 15 days to ensure 'increasing' is triggered
    for i in range(15):
        d = now - timedelta(days=15 - i)
        eid = db.create_journal_entry(user_id, f"Stress {i}", {})
        db.add_theme_occurrence(t_stress, 'journal_entry', eid, "stress", 0.95, d.isoformat())
        db.update_theme_stats(t_stress, d.isoformat())

    # --- 2. FORCED CONFLICTING RESOLUTION (Dissipated) ---
    # We manually create a conflict record in the registry
    # Note: In real life this would come from the engine, but we're testing the suppression gate.
    db.create_or_update_resolution(
        pattern_type='theme',
        pattern_id=t_stress,
        resolution_label='dissipated',
        attenuation_score=1.0,
        confidence_level='medium',
        recent_count=0,
        past_count=10
    )
    # We also need a confidence record for it
    db.create_or_update_confidence('resolution', t_stress, 'medium', 0.6, 10, 30, 1.0, 0.5)

    # Run Trajectory to populate its confidence/result
    traj_result = TrajectoryEngine(user_id).analyze_theme(t_stress)
    print(f"DEBUG: Trajectory Label: {traj_result['trajectory_label']}")

    # --- 3. VERIFY SUPPRESSION ---
    companion = PersonalAICompanion(user_id=user_id)
    companion.intelligence.chat = MagicMock(return_value="OK")
    companion.chat("Conflict test.")
    
    prompt = companion.intelligence.chat.call_args[1]['system_prompt']
    
    print("\n--- CONFLICT ANALYSIS ---")
    # Section check
    stress_increasing = "is increasing in frequency" in prompt or "Work Stress" in prompt
    stress_dissipated = "appeared frequently in the past but has not appeared recently" in prompt
    
    status_inc = "[OK]" if stress_increasing else "[MISSING]"
    status_dis = "[SUPPRESSED]" if not stress_dissipated else "[CONFLICT DETECTED]"
    
    print(f"Trajectory Winner in Prompt: {status_inc}")
    print(f"Resolution Loser in Prompt: {status_dis}")
    
    assert stress_increasing, "High confidence winner was incorrectly removed"
    assert not stress_dissipated, "Losing contradictory insight was not suppressed"

    logger.info("System Meta-Control Integration Test Passed.")

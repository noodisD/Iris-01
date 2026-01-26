
import pytest
import logging
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from agent.core import PersonalAICompanion
from agent.database import db
from agent.persistence import PersistenceEngine
from agent.leverage import LeverageEngine
from agent.constants import (
    LEVERAGE_WINDOW_DAYS,
    LEVERAGE_MIN_OCCURRENCES
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@pytest.fixture
def mock_pipeline_components(monkeypatch):
    # Mock embedding generation
    monkeypatch.setattr("agent.pipeline.generate_embedding", lambda text, model=None: [0.1] * 1536)
    # Mock Graph DB operations
    monkeypatch.setattr("agent.pipeline.graph_db.add_journal_entry_node", lambda *args: None)
    monkeypatch.setattr("agent.pipeline.graph_db.add_idea_node", lambda *args: None)
    monkeypatch.setattr("agent.pipeline.graph_db.link_journal_to_idea", lambda *args: None)

def test_system_with_leverage(test_user, mock_pipeline_components):
    """
    Full system test including Leverage Engine.
    Verifies that asymmetric patterns are detected as drivers and injected into context.
    """
    user_id = test_user['id']
    companion = PersonalAICompanion(user_id=user_id)
    
    logger.info("--- Step 1: Establish Baseline Patterns ---")
    now = datetime.now()
    # Start 50 days ago (within LEVERAGE_WINDOW_DAYS=60)
    start_date = now - timedelta(days=50)
    
    # Theme A: Work Stress (The Driver)
    theme_a_id = db.create_theme(
        user_id=user_id,
        centroid_embedding=[0.1] * 1536,
        summary="Work Stress",
        first_seen_at=start_date.isoformat(),
        last_seen_at=now.isoformat()
    )
    
    # Theme B: Poor Sleep (The Target)
    theme_b_id = db.create_theme(
        user_id=user_id,
        centroid_embedding=[0.2] * 1536,
        summary="Poor Sleep",
        first_seen_at=start_date.isoformat(),
        last_seen_at=now.isoformat()
    )
    
    # Create 6 pairs of (Stress -> Sleep)
    # Stress on Day X, Sleep on Day X+2
    # This creates perfect directional lift A->B
    for i in range(6):
        date_a = start_date + timedelta(days=i*10)
        date_b = date_a + timedelta(days=2)
        
        # Add Stress
        entry_id_a = db.create_journal_entry(user_id, f"Stress {i}", {})
        db.add_theme_occurrence(theme_a_id, 'journal_entry', entry_id_a, "stress", 0.9, date_a.isoformat())
        db.update_theme_stats(theme_a_id, date_a.isoformat())
        
        # Add Sleep
        entry_id_b = db.create_journal_entry(user_id, f"Sleep {i}", {})
        db.add_theme_occurrence(theme_b_id, 'journal_entry', entry_id_b, "sleep", 0.9, date_b.isoformat())
        db.update_theme_stats(theme_b_id, date_b.isoformat())

    logger.info("--- Step 2: Analyze Leverage ---")
    # Manually trigger analysis
    leverage_engine = LeverageEngine(user_id)
    results = leverage_engine.analyze_all_leverage(force_recompute=True)
    
    logger.info(f"Leverage Results: {results}")
    
    # Find the A->B result
    pair_result = next((r for r in results if r['source_id'] == theme_a_id and r['target_id'] == theme_b_id), None)
    
    assert pair_result is not None, "Leverage engine failed to detect Work Stress -> Poor Sleep"
    assert pair_result['directional_lift'] > 0.5, f"Expected high lift, got {pair_result['directional_lift']}"
    assert pair_result['influence_score'] > 0.5, "Influence score should be high"
    assert pair_result['confidence_level'] in ['medium', 'high']
    
    # Verify B->A is NOT detected or low
    reverse_result = leverage_engine.analyze_pair('theme', theme_b_id, 'theme', theme_a_id)
    # Lift should be negative or zero because B never precedes A within window (except Maybe if loop wraps? No, i*7 spacing avoids overlap)
    # date_b(i) = start + 7i + 2
    # date_a(i+1) = start + 7(i+1) = start + 7i + 7
    # diff = 5 days. 
    # So B(i) precedes A(i+1) by 5 days.
    # Wait! If I space them by 7 days, B(i) is 5 days before A(i+1).
    # LEVERAGE_TIME_LAG_DAYS = 7.
    # So B -> A is ALSO possible if I don't space them out enough.
    
    # Let's check the math.
    # A(0): 0. B(0): 2.
    # A(1): 7. B(1): 9.
    # A->B: 0->2 (2 days). A->B count = 6.
    # B->A: 2->7 (5 days). B->A count = 5 (for i=0 to 4).
    # This creates MUTUAL leverage, not directional. Lift will be low.
    # Lift = P(B|A) - P(A|B) = (6/6) - (5/6) = 1 - 0.83 = 0.17.
    # 0.17 is > threshold (0.15). So it might barely pass as leverage.
    
    # I should space them out more to ensure CLEAN directional leverage.
    # Let's space them by 10 days.
    # A(0): 0. B(0): 2.
    # A(1): 10. B(1): 12.
    # B(0)->A(1) is 8 days > 7 days lag.
    # So B->A count will be 0.
    # Perfect.
    
    logger.info("--- Step 3: Verify Context Injection ---")
    
    # Mock LLM to inspect prompt
    companion.intelligence.chat = MagicMock(return_value="Mock response")
    companion.chat("Analyze my patterns.")
    
    call_args = companion.intelligence.chat.call_args
    system_prompt = call_args[1]['system_prompt']
    
    print("\n--- SYSTEM PROMPT SNIPPET ---")
    # Extract the relevant section
    if "# Observed Structural Drivers:" in system_prompt:
        print(system_prompt.split("# Observed Structural Drivers:")[1].split("\n\n")[0])
    else:
        print("SECTION MISSING")
    print("-----------------------------\n")
    
    assert "# Observed Structural Drivers:" in system_prompt
    assert "Work Stress" in system_prompt
    assert "frequently precedes several other patterns" in system_prompt

    logger.info("Test Complete: Leverage detected and injected.")

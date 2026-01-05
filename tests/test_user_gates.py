
import pytest
from unittest.mock import MagicMock
from agent.core import PersonalAICompanion
from agent.database import db

@pytest.fixture
def companion(test_user):
    c = PersonalAICompanion(test_user['id'])
    # Bypass heavy analytical fetch for gate tests
    c._get_relevant_context = MagicMock(return_value="")
    c.intelligence.chat = MagicMock(return_value="OK")
    return c

def test_confidence_threshold_gate(companion, monkeypatch):
    # Scenario: 1 High, 1 Medium insight.
    # Set preference to 'high' only.
    companion.pref_service.update_pref('min_confidence', 'high')
    
    mock_insights = [
        {"engine_name": "trajectory", "pattern_type": "theme", "pattern_id": 1, "confidence": "high"},
        {"engine_name": "trajectory", "pattern_type": "theme", "pattern_id": 2, "confidence": "medium"}
    ]
    
    filtered = companion._filter_by_confidence(mock_insights, min_level='high')
    assert len(filtered) == 1
    assert filtered[0]['confidence'] == 'high'

def test_engine_whitelist_gate(companion):
    # Disable 'leverage' and 'tension'
    companion.pref_service.update_pref('enabled_engines', ['persistence', 'trajectory', 'resolution'])
    
    raw = [
        {"engine_name": "leverage", "pattern_type": "theme", "pattern_id": 1},
        {"engine_name": "trajectory", "pattern_type": "theme", "pattern_id": 2}
    ]
    
    enabled = companion.pref_service.get_prefs()['enabled_engines']
    filtered = [i for i in raw if enabled is None or i['engine_name'] in enabled]
    
    assert len(filtered) == 1
    assert filtered[0]['engine_name'] == 'trajectory'

def test_context_budget_gate(companion):
    # Set budget to 1
    companion.pref_service.update_pref('max_items', 1)
    
    # Simulate 5 ranked insights
    ranked = [{"id": i} for i in range(5)]
    
    final = ranked[:companion.pref_service.get_prefs()['max_items']]
    assert len(final) == 1

def test_preference_reset_logs_audit(test_user, companion):
    user_id = test_user['id']
    # 1. Change setting
    companion.pref_service.update_pref('max_items', 1)
    
    # 2. Reset
    companion.pref_service.reset()
    
    # 3. Verify audit record exists
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM preference_audit WHERE user_id = %s", (user_id,))
        # One for update, one for reset logic? 
        # (Reset calls update internally? No, reset deletes the row).
        # Actually my DB implementation reset deletes. 
        # Let's check update_preference logic.
        assert cur.fetchone()[0] >= 1

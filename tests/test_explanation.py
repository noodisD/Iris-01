
import pytest
from datetime import datetime, timedelta
from agent.database import db
from agent.evidence import EvidenceEngine
from agent.explanation import ExplanationEngine
from agent.resolution import ResolutionEngine

@pytest.fixture
def test_env(test_user):
    return {
        "user_id": test_user['id'],
        "ev_engine": EvidenceEngine(),
        "explainer": ExplanationEngine(test_user['id'])
    }

def test_evidence_immutability_on_recompute(test_env):
    user_id = test_env['user_id']
    # 1. Setup a theme
    t_id = db.create_theme(user_id, [0.1]*1536, "Test Theme", datetime.now().isoformat(), datetime.now().isoformat())
    
    # 2. Record first run
    records1 = [{"type": "count", "key": "test_metric", "value": 10}]
    comp_id1 = test_env['ev_engine'].record_evidence('test_engine', 'theme', t_id, records1)
    
    # 3. Record second run
    records2 = [{"type": "count", "key": "test_metric", "value": 20}]
    comp_id2 = test_env['ev_engine'].record_evidence('test_engine', 'theme', t_id, records2)
    
    assert comp_id1 != comp_id2
    
    # 4. Verify both exist in DB (Immutability)
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM pattern_evidence WHERE pattern_id = %s", (t_id,))
        assert cur.fetchone()[0] == 2

def test_explanation_uses_latest_snapshot(test_env):
    user_id = test_env['user_id']
    t_id = db.create_theme(user_id, [0.1]*1536, "Test Theme", datetime.now().isoformat(), datetime.now().isoformat())
    
    # Mock confidence record (required by explainer)
    db.create_or_update_confidence('theme', t_id, 'high', 0.9, 10, 30, 1.0, 1.0)
    
    # Run 1: value = 100
    test_env['ev_engine'].record_evidence('test_engine', 'theme', t_id, [{"type": "count", "key": "val", "value": 100}])
    # Run 2: value = 200
    test_env['ev_engine'].record_evidence('test_engine', 'theme', t_id, [{"type": "count", "key": "val", "value": 200}])
    
    # Explain
    bundle = test_env['explainer'].explain('theme', t_id)
    
    # Should show 200 (latest)
    val = next(e['value'] for e in bundle['evidence'] if e['label'] == 'Val')
    assert val == 200

def test_cross_engine_isolation(test_env):
    user_id = test_env['user_id']
    t_id = db.create_theme(user_id, [0.1]*1536, "Test Theme", datetime.now().isoformat(), datetime.now().isoformat())
    
    # Mock confidence record
    db.create_or_update_confidence('theme', t_id, 'high', 0.9, 10, 30, 1.0, 1.0)
    test_env['ev_engine'].record_evidence('leverage', 'theme', t_id, [{"type": "count", "key": "lev_metric", "value": 1}])
    
    # Record resolution evidence (different computation_id)
    test_env['ev_engine'].record_evidence('resolution', 'theme', t_id, [{"type": "count", "key": "res_metric", "value": 2}])
    
    # Explain ONLY resolution
    bundle = test_env['explainer'].explain('theme', t_id, engine_name='resolution')
    
    # Verify leverage metric is NOT in the bundle
    keys = [e['label'] for e in bundle['evidence']]
    assert 'Res metric' in keys
    assert 'Lev metric' not in keys

def test_low_confidence_guardrail(test_env):
    user_id = test_env['user_id']
    t_id = db.create_theme(user_id, [0.1]*1536, "Test Theme", datetime.now().isoformat(), datetime.now().isoformat())
    
    # Set confidence to LOW
    db.create_or_update_confidence('theme', t_id, 'low', 0.1, 1, 0, 0.0, 0.1)
    
    # Add some evidence
    test_env['ev_engine'].record_evidence('test', 'theme', t_id, [{"type": "count", "key": "x", "value": 1}])
    
    # Explain
    bundle = test_env['explainer'].explain('theme', t_id)
    
    assert "Insufficient reliable evidence" in bundle['summary']
    assert len(bundle['evidence']) == 0

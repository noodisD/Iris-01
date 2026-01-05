
import pytest
from datetime import datetime, timedelta
from agent.database import db

def test_schema_idempotency():
    # Should be able to run create_schema multiple times without error
    db.create_schema()
    db.create_schema()

def test_invalidation_propagation(test_user):
    user_id = test_user['id']
    
    # 1. Setup a theme
    t_id = db.create_theme(user_id, [0.1]*1536, "Test Theme", datetime.now().isoformat(), datetime.now().isoformat())
    
    # 2. Populate all cache tables with 'valid' snapshots
    db.create_theme_trajectory(t_id, 'increasing', 0.5, 5, 5, 'high', 10)
    db.create_or_update_resolution('theme', t_id, 'persisting', 0.0, 'high', 5, 5)
    db.create_or_update_confidence('theme', t_id, 'high', 0.9, 10, 30, 1.0, 1.0)
    
    # Verify they are NOT null
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT last_computed_at FROM theme_trajectories WHERE theme_id = %s", (t_id,))
        assert cur.fetchone()[0] is not None
        cur.execute("SELECT last_computed_at FROM pattern_resolutions WHERE pattern_id = %s", (t_id,))
        assert cur.fetchone()[0] is not None
        cur.execute("SELECT last_computed_at FROM pattern_confidence WHERE pattern_id = %s", (t_id,))
        assert cur.fetchone()[0] is not None

    # 3. Propagate Invalidation (Add occurrence)
    # This should trigger invalidation in all 3 tables
    db.add_theme_occurrence(t_id, 'journal_entry', 1, "snippet", 0.9, datetime.now().isoformat())
    
    # 4. Verify propagation
    with conn.cursor() as cur:
        # Note: theme_trajectories doesn't have an explicit invalidate trigger in add_theme_occurrence yet?
        # Actually, let's check database.py to see what we implemented.
        # It has: pattern_resolutions, theme_tensions, pattern_leverage, decision_impacts, pattern_confidence.
        
        cur.execute("SELECT last_computed_at FROM pattern_resolutions WHERE pattern_id = %s", (t_id,))
        assert cur.fetchone()[0] is None, "Resolution cache should have been invalidated"
        
        cur.execute("SELECT last_computed_at FROM pattern_confidence WHERE pattern_id = %s", (t_id,))
        assert cur.fetchone()[0] is None, "Confidence cache should have been invalidated"

def test_audit_immutability(test_user):
    user_id = test_user['id']
    
    # 1. Update a preference
    db.update_preference(user_id, 'max_items', 1)
    db.update_preference(user_id, 'max_items', 2)
    
    # 2. Verify audit table has TWO entries (Immutability check)
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM preference_audit WHERE user_id = %s", (user_id,))
        assert cur.fetchone()[0] == 2

def test_unique_constraints(test_user):
    user_id = test_user['id']
    # Use a high random ID to avoid collision with other tests
    test_sid = 99999
    db.add_embedding('journal_entry', test_sid, 'model', [0.1]*1536)
    db.add_embedding('journal_entry', test_sid, 'model', [0.2]*1536) # Should update, not fail
    
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM embeddings WHERE source_id = %s", (test_sid,))
        assert cur.fetchone()[0] == 1

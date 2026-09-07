
from datetime import datetime

from agent.database import db


def test_schema_idempotency():
    """Migrating an already-migrated database changes nothing and applies
    nothing, rather than re-running DDL."""
    from agent import migrations

    before = migrations.current_version()
    assert migrations.upgrade() == [], "a second upgrade must be a no-op"
    assert migrations.current_version() == before

def test_invalidation_propagation(test_user):
    user_id = test_user['id']

    # 1. Setup a theme
    t_id = db.create_theme(user_id, [0.1]*1536, "Test Theme", datetime.now().isoformat(), datetime.now().isoformat())

    # 2. Populate the cache tables with 'valid' snapshots. theme_trajectories
    # used to be one of them; it had no reader and was dropped in migration
    # 0004 (ADR-0005), so trajectory is recomputed rather than invalidated.
    db.create_or_update_resolution('theme', t_id, 'persisting', 0.0, 'high', 5, 5)
    db.create_or_update_confidence('theme', t_id, 'high', 0.9, 10, 30, 1.0, 1.0)

    # Verify they are NOT null
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT last_computed_at FROM pattern_resolutions WHERE pattern_id = %s", (t_id,))
        assert cur.fetchone()[0] is not None
        cur.execute("SELECT last_computed_at FROM pattern_confidence WHERE pattern_id = %s", (t_id,))
        assert cur.fetchone()[0] is not None

    # 3. Propagate Invalidation (Add occurrence)
    db.add_theme_occurrence(t_id, 'journal_entry', 1, "snippet", 0.9, datetime.now().isoformat())

    # 4. Verify propagation
    with conn.cursor() as cur:
        # add_theme_occurrence invalidates pattern_resolutions, theme_tensions,
        # pattern_leverage, decision_impacts and pattern_confidence.
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
    # Use a high random ID to avoid collision with other tests
    test_sid = 99999
    db.add_embedding('journal_entry', test_sid, 'model', [0.1]*1536)
    db.add_embedding('journal_entry', test_sid, 'model', [0.2]*1536) # Should update, not fail

    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM embeddings WHERE source_id = %s", (test_sid,))
        assert cur.fetchone()[0] == 1


def test_deleting_a_user_takes_their_data_with_them():
    """Twelve of the fifteen foreign keys to users(id) cascaded; three did not,
    so DELETE FROM users raised a foreign key violation unless
    conversation_messages, journal_entries and themes were cleared by hand
    first. "Delete everything about me" could not be implemented correctly
    without remembering those three exceptions. Migration 0003 made them
    consistent."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s,'x') RETURNING id;",
            (f"cascade_{datetime.now().timestamp()}",),
        )
        user_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO journal_entries (user_id, raw_text) VALUES (%s,'j');", (user_id,)
        )
        cur.execute(
            """INSERT INTO conversation_messages (user_id, session_id, role, content)
               VALUES (%s,'s','user','m');""",
            (user_id,),
        )
        cur.execute(
            """INSERT INTO themes (user_id, centroid_embedding, summary,
                                   first_seen_at, last_seen_at)
               VALUES (%s,%s,'t',NOW(),NOW()) RETURNING id;""",
            (user_id, [0.1] * 1536),
        )
        theme_id = cur.fetchone()[0]
        cur.execute(
            """INSERT INTO theme_occurrences (theme_id, source_type, source_id,
                                              snippet, similarity_score, occurred_at)
               VALUES (%s,'journal_entry',1,'s',0.9,NOW());""",
            (theme_id,),
        )
        conn.commit()

        # One statement, no manual cleanup. This used to raise.
        cur.execute("DELETE FROM users WHERE id = %s;", (user_id,))
        conn.commit()

        for table in ("journal_entries", "conversation_messages", "themes"):
            cur.execute(f"SELECT count(*) FROM {table} WHERE user_id = %s;", (user_id,))
            assert cur.fetchone()[0] == 0, f"{table} rows outlived the user"
        cur.execute(
            "SELECT count(*) FROM theme_occurrences WHERE theme_id = %s;", (theme_id,)
        )
        assert cur.fetchone()[0] == 0, "occurrences must go with their theme"

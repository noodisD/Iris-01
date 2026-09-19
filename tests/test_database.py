"""
Tests for the Database layer (Source of Truth).
"""

import uuid

from agent.database import db


def test_create_and_get_user(setup_test_database):
    """Test creating and retrieving a user."""
    # Create a unique username to avoid conflicts
    unique_username = f"testuser_{uuid.uuid4().hex[:8]}"

    # Create a user first
    user_id = db.create_user(unique_username)
    assert user_id is not None

    # Then retrieve it
    user = db.get_user(unique_username)
    assert user is not None
    assert user["username"] == unique_username

def test_there_is_one_local_user_and_no_password(setup_test_database):
    """The CLI had its own login, its own users, and unsalted SHA-256 hashes,
    in front of the database the HTTP app serves to one user with no login
    (ADR-0001). Both front doors resolve the same user now, and nothing stores
    a password."""
    name = f"local_{uuid.uuid4().hex[:8]}"
    first, again = db.local_user_id(name), db.local_user_id(name)
    assert first == again, "one user, created once"
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT password_hash FROM users WHERE id = %s;", (first,))
        assert cur.fetchone()[0] is None
        cur.execute("DELETE FROM users WHERE id = %s;", (first,))
        conn.commit()

def test_create_journal_entry(test_user):
    """Test creating a journal entry."""
    entry_id = db.create_journal_entry(
        user_id=test_user["id"],
        raw_text="This is a test journal entry.",
        wellbeing_data={"mood": 8}
    )
    assert isinstance(entry_id, int)

def test_create_conversation_message(test_user):
    """Test creating a conversation message."""
    message_id = db.create_conversation_message(
        user_id=test_user["id"],
        session_id="test_session",
        role="user",
        content="Hello, world!"
    )
    assert isinstance(message_id, int)

def test_add_and_get_embedding(test_user):
    """Test adding and retrieving an embedding."""
    entry_id = db.create_journal_entry(
        user_id=test_user["id"],
        raw_text="Entry to be embedded.",
        wellbeing_data={"mood": 5}
    )

    model_name = "test_model"
    vector = [0.1] * 1536  # Correct dimension for the schema

    db.add_embedding(
        source_type="journal_entry",
        source_id=entry_id,
        model_name=model_name,
        vector=vector
    )

    # This requires a 'get_embedding' method in database.py, which we add now for testing
    def get_embedding(source_type, source_id, model_name):
        conn = db.get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT vector FROM embeddings WHERE source_type = %s AND source_id = %s AND model_name = %s;",
                (source_type, source_id, model_name)
            )
            result = cur.fetchone()
            return result[0] if result else None

    retrieved_vector = get_embedding("journal_entry", entry_id, model_name)
    assert retrieved_vector is not None
    assert len(retrieved_vector) == 1536
    assert retrieved_vector[0] == 0.1

def test_update_and_get_processing_status(test_user):
    """Test updating and retrieving item processing status."""
    entry_id = db.create_journal_entry(
        user_id=test_user["id"],
        raw_text="Another test entry.",
        wellbeing_data={"mood": 7}
    )

    db.update_processing_status("journal_entry", entry_id, "complete")

    # We need a way to get the status to verify
    def get_status(source_type, source_id):
        table_name = "journal_entries" if source_type == "journal_entry" else "conversation_messages"
        conn = db.get_connection()
        with conn.cursor() as cur:
            cur.execute(f"SELECT processing_status FROM {table_name} WHERE id = %s;", (source_id,))
            result = cur.fetchone()
            return result[0] if result else None

    status = get_status("journal_entry", entry_id)
    assert status == "complete"

def test_theme_operations(test_user):
    """Test creating and managing themes."""
    centroid = [0.2] * 1536
    summary = "Test Theme"
    first_seen = "2024-01-01T10:00:00Z"
    last_seen = "2024-01-01T10:00:00Z"

    theme_id = db.create_theme(
        user_id=test_user["id"],
        centroid_embedding=centroid,
        summary=summary,
        first_seen_at=first_seen,
        last_seen_at=last_seen
    )
    assert isinstance(theme_id, int)

    # Test get_themes
    themes = db.get_themes(test_user["id"])
    assert len(themes) >= 1
    assert any(t["id"] == theme_id for t in themes)

    # Test update_theme_stats. The count is derived from the occurrences that
    # exist, not incremented: this used to add one per call whether or not any
    # evidence had been recorded, so a redelivered source counted twice and a
    # theme's count drifted away from the occurrences supporting it.
    db.add_theme_occurrence(theme_id, 'journal_entry', 9001, "one", 0.9,
                            "2024-01-01T10:00:00Z")
    db.add_theme_occurrence(theme_id, 'journal_entry', 9002, "two", 0.9,
                            "2024-01-02T10:00:00Z")
    db.update_theme_stats(theme_id, "2024-01-02T10:00:00Z")

    updated_themes = db.get_themes(test_user["id"])
    theme = next(t for t in updated_themes if t["id"] == theme_id)
    assert theme["occurrence_count"] == 2
    assert theme["last_seen_at"] is not None

    # Delivering the same source again is a no-op, not another occurrence.
    db.add_theme_occurrence(theme_id, 'journal_entry', 9002, "two", 0.9,
                            "2024-01-02T10:00:00Z")
    db.update_theme_stats(theme_id, "2024-01-02T10:00:00Z")
    theme = next(t for t in db.get_themes(test_user["id"]) if t["id"] == theme_id)
    assert theme["occurrence_count"] == 2, "a replayed source must not be counted twice"

def test_theme_occurrence_operations(test_user):
    """Test theme occurrence tracking."""
    # Setup: need a theme and an entry
    theme_id = db.create_theme(
        user_id=test_user["id"],
        centroid_embedding=[0.3]*1536,
        summary="Recurring Idea",
        first_seen_at="2024-01-01T10:00:00Z",
        last_seen_at="2024-01-01T10:00:00Z"
    )

    entry_id = db.create_journal_entry(
        user_id=test_user["id"],
        raw_text="I keep thinking about this idea.",
        wellbeing_data={}
    )

    # Test add_theme_occurrence
    db.add_theme_occurrence(
        theme_id=theme_id,
        source_type="journal_entry",
        source_id=entry_id,
        snippet="thinking about this idea",
        similarity_score=0.95,
        occurred_at="2024-01-01T10:00:00Z"
    )

    # Test get_theme_occurrences
    occurrences = db.get_theme_occurrences(theme_id)
    assert len(occurrences) == 1
    assert occurrences[0]["source_id"] == entry_id
    assert occurrences[0]["similarity_score"] == 0.95

def test_unassigned_embeddings(test_user):
    """Test finding embeddings not yet assigned to themes."""
    # 1. Create entry and embedding
    entry_id = db.create_journal_entry(test_user["id"], "Unassigned entry", {})
    vector = [0.4] * 1536
    db.add_embedding("journal_entry", entry_id, "test_model", vector)

    # 2. Check unassigned
    unassigned = db.get_unassigned_embeddings(test_user["id"])
    assert any(u["source_id"] == entry_id for u in unassigned)

    # 3. Assign to a theme
    theme_id = db.create_theme(test_user["id"], vector, "Unassigned Theme", "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z")
    db.add_theme_occurrence(theme_id, "journal_entry", entry_id, "snippet", 1.0, "2024-01-01T00:00:00Z")

    # 4. Should no longer be unassigned
    unassigned_after = db.get_unassigned_embeddings(test_user["id"])
    assert not any(u["source_id"] == entry_id for u in unassigned_after)

"""
Tests for the Database layer (Source of Truth).
"""

from agent.database import db

def test_create_and_get_user(setup_test_database):
    """Test creating and retrieving a user."""
    user = db.get_user("testuser")
    assert user is not None
    assert user["username"] == "testuser"

def test_verify_user(test_user):
    """Test user password verification."""
    verified_user = db.verify_user("testuser", "testpassword")
    assert verified_user is not None
    assert verified_user["id"] == test_user["id"]
    
    unverified_user = db.verify_user("testuser", "wrongpassword")
    assert unverified_user is None

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
    
    # Test update_theme_stats
    new_last_seen = "2024-01-02T10:00:00Z"
    db.update_theme_stats(theme_id, new_last_seen)
    
    updated_themes = db.get_themes(test_user["id"])
    theme = next(t for t in updated_themes if t["id"] == theme_id)
    assert theme["occurrence_count"] == 2
    assert theme["last_seen_at"] is not None

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
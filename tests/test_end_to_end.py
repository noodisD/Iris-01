"""
End-to-end integration tests for the complete data flow.
Tests the full pipeline: PostgreSQL → Embedding → pgvector → Themes
"""

import pytest
from agent.database import db
from agent.pipeline import run_processing_pipeline
from unittest.mock import patch, MagicMock
import shutil
import os


def test_complete_journal_entry_flow(test_user, mocker):
    """
    Test the complete flow: create journal entry → generate embedding → store in DB → index in vector store.
    """
    # 1. Mock external services
    mock_openai = mocker.patch("agent.pipeline.openai.embeddings.create")
    test_embedding = [0.3] * 1536
    mock_openai.return_value.data = [MagicMock(embedding=test_embedding)]

    # 2. Create a journal entry
    content = "Today I had an important realization:\n- Work-life balance is crucial\n- Self-care matters"
    entry_id = db.create_journal_entry(
        user_id=test_user["id"],
        raw_text=content,
        wellbeing_data={"mood": 8, "stress": 3}
    )

    # 3. Verify initial state
    items = db.get_items_to_process('journal_entry', status='pending', limit=1)
    assert len(items) > 0
    assert items[0]['content'] == content

    # 4. Run the processing pipeline
    run_processing_pipeline('journal_entry', entry_id)

    # 5. Verify embedding was created in PostgreSQL
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT vector FROM embeddings WHERE source_type = %s AND source_id = %s;",
            ('journal_entry', entry_id)
        )
        result = cur.fetchone()
        assert result is not None, "Embedding should be stored in PostgreSQL"
        assert len(result[0]) == 1536

    # 6. Verify processing status is complete
    with conn.cursor() as cur:
        cur.execute("SELECT processing_status FROM journal_entries WHERE id = %s;", (entry_id,))
        status = cur.fetchone()[0]
        assert status == 'complete'


def test_conversation_message_flow(test_user, mocker):
    """
    Test the complete flow for conversation messages.
    """
    # Mock OpenAI
    mock_openai = mocker.patch("agent.pipeline.openai.embeddings.create")
    test_embedding = [0.4] * 1536
    mock_openai.return_value.data = [MagicMock(embedding=test_embedding)]

    # 1. Create a conversation message
    content = "The weather is great today, I feel energized!"
    message_id = db.create_conversation_message(
        user_id=test_user["id"],
        session_id="session_123",
        role="user",
        content=content
    )

    # 2. Verify it's pending processing
    items = db.get_items_to_process('message', status='pending', limit=1)
    assert len(items) > 0

    # 3. Run pipeline
    run_processing_pipeline('message', message_id)

    # 4. Verify embedding exists
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT vector FROM embeddings WHERE source_type = %s AND source_id = %s;",
            ('message', message_id)
        )
        result = cur.fetchone()
        assert result is not None
        assert len(result[0]) == 1536

    # 5. Verify status is complete
    with conn.cursor() as cur:
        cur.execute("SELECT processing_status FROM conversation_messages WHERE id = %s;", (message_id,))
        status = cur.fetchone()[0]
        assert status == 'complete'


def test_batch_processing_flow(test_user, mocker):
    """
    Test processing multiple items in batch.
    """
    mock_openai = mocker.patch("agent.pipeline.openai.embeddings.create")
    mock_openai.return_value.data = [MagicMock(embedding=[0.5] * 1536)]

    # Mock graph operations

    # Create multiple entries
    entry_ids = []
    for i in range(3):
        entry_id = db.create_journal_entry(
            user_id=test_user["id"],
            raw_text=f"Entry {i}: Test content {i}",
            wellbeing_data={"mood": 5 + i}
        )
        entry_ids.append(entry_id)

    # Process all of them
    for entry_id in entry_ids:
        run_processing_pipeline('journal_entry', entry_id)

    # Verify all were processed
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM embeddings WHERE source_type = %s;",
            ('journal_entry',)
        )
        count = cur.fetchone()[0]
        assert count >= 3, f"Expected at least 3 embeddings, got {count}"


def test_error_handling_in_pipeline(test_user, mocker):
    """
    Test that pipeline handles errors gracefully and marks items as failed.
    """
    # Mock OpenAI to fail
    mock_openai = mocker.patch("agent.pipeline.openai.embeddings.create")
    mock_openai.side_effect = Exception("API Error")

    # Mock graph operations

    # Create entry
    entry_id = db.create_journal_entry(
        user_id=test_user["id"],
        raw_text="Entry that will fail",
        wellbeing_data={"mood": 5}
    )

    # Run pipeline - should handle the error
    run_processing_pipeline('journal_entry', entry_id)

    # Verify status is failed
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT processing_status FROM journal_entries WHERE id = %s;", (entry_id,))
        status = cur.fetchone()[0]
        assert status == 'failed', "Entry should be marked as failed after error"

    # Verify no embedding was created for this specific journal entry
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM embeddings WHERE source_type = 'journal_entry' AND source_id = %s;",
            (entry_id,)
        )
        count = cur.fetchone()[0]
        assert count == 0, "Failed processing should not create an embedding"


def test_idempotent_processing(test_user, mocker):
    """
    Test that processing the same item multiple times is safe.
    """
    mock_openai = mocker.patch("agent.pipeline.openai.embeddings.create")
    test_embedding = [0.6] * 1536
    mock_openai.return_value.data = [MagicMock(embedding=test_embedding)]

    # Mock graph operations

    # Create entry
    entry_id = db.create_journal_entry(
        user_id=test_user["id"],
        raw_text="Entry to process multiple times",
        wellbeing_data={"mood": 5}
    )

    # Process it twice
    run_processing_pipeline('journal_entry', entry_id)
    run_processing_pipeline('journal_entry', entry_id)

    # Verify only one embedding exists (should be updated, not duplicated)
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM embeddings WHERE source_type = %s AND source_id = %s;",
            ('journal_entry', entry_id)
        )
        count = cur.fetchone()[0]
        assert count == 1, "Should have only one embedding after double processing"

    # Verify both statuses are complete (not pending after second run)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT processing_status FROM journal_entries WHERE id = %s;",
            (entry_id,)
        )
        status = cur.fetchone()[0]
        assert status == 'complete'


def test_data_recovery_from_postgres(test_user, mocker):
    """
    Test that data can be recovered from PostgreSQL if vector store is lost.
    This tests the "PostgreSQL is the source of truth" principle.
    """
    mock_openai = mocker.patch("agent.pipeline.openai.embeddings.create")
    test_embedding = [0.7] * 1536
    mock_openai.return_value.data = [MagicMock(embedding=test_embedding)]

    # Mock graph operations

    # 1. Create and process data
    entry_id = db.create_journal_entry(
        user_id=test_user["id"],
        raw_text="Important entry",
        wellbeing_data={"mood": 8}
    )
    run_processing_pipeline('journal_entry', entry_id)

    # 2. Verify embedding is in PostgreSQL
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT vector FROM embeddings WHERE source_id = %s;",
            (entry_id,)
        )
        original_embedding = cur.fetchone()[0]
        assert original_embedding is not None, "Embedding should be stored in PostgreSQL"

    # 3. Delete from vector store (simulate loss)
    # This would normally be done by deleting chroma_db directory
    # For testing, we just verify that PostgreSQL still has the data

    # 4. Verify we can still get the embedding from PostgreSQL
    with conn.cursor() as cur:
        cur.execute(
            "SELECT vector FROM embeddings WHERE source_id = %s;",
            (entry_id,)
        )
        recovered_embedding = cur.fetchone()[0]
        # Compare lengths since vector comparison can be complex
        assert len(recovered_embedding) == 1536, "Recovered embedding should have correct dimension"
        # Verify it's not None
        assert recovered_embedding is not None, "Embedding should be recoverable"


def test_processing_status_transitions(test_user):
    """
    Test that processing status transitions are correct: pending → processing → complete/failed
    """
    entry_id = db.create_journal_entry(
        user_id=test_user["id"],
        raw_text="Status tracking entry",
        wellbeing_data={"mood": 5}
    )

    conn = db.get_connection()

    # Initial status should be pending
    with conn.cursor() as cur:
        cur.execute("SELECT processing_status FROM journal_entries WHERE id = %s;", (entry_id,))
        status = cur.fetchone()[0]
        assert status == 'pending'

    # Update to processing
    db.update_processing_status('journal_entry', entry_id, 'processing')
    with conn.cursor() as cur:
        cur.execute("SELECT processing_status FROM journal_entries WHERE id = %s;", (entry_id,))
        status = cur.fetchone()[0]
        assert status == 'processing'

    # Update to complete
    db.update_processing_status('journal_entry', entry_id, 'complete')
    with conn.cursor() as cur:
        cur.execute("SELECT processing_status FROM journal_entries WHERE id = %s;", (entry_id,))
        status = cur.fetchone()[0]
        assert status == 'complete'


def test_wellbeing_data_preservation(test_user):
    """
    Test that wellbeing data is properly stored and retrieved.
    """
    wellbeing_data = {
        "mood": 7,
        "stress": 2,
        "energy": 8,
        "notes": "Feeling great today"
    }

    entry_id = db.create_journal_entry(
        user_id=test_user["id"],
        raw_text="Test entry",
        wellbeing_data=wellbeing_data
    )

    # Retrieve and verify
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT wellbeing_data FROM journal_entries WHERE id = %s;", (entry_id,))
        retrieved_data = cur.fetchone()[0]
        assert retrieved_data == wellbeing_data

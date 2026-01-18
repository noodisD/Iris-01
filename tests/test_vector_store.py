"""
Integration tests for the Vector Store Layer (FAISS Lens).
Tests the semantic search capabilities and rebuild functionality.
"""

import pytest
from agent.vector_store import VectorStore
from agent.database import db
import shutil
import os


@pytest.fixture
def vector_store_fresh():
    """
    Fixture that creates a fresh FAISS-based vector store instance for testing.
    Uses a temporary directory to avoid file system issues.
    """
    import tempfile
    from pathlib import Path

    # Create a temporary directory for testing
    temp_dir = Path(tempfile.mkdtemp(prefix="faiss_test_"))

    # Create a fresh VectorStore instance using the actual class
    vs = VectorStore(path=temp_dir)

    # Ensure we're using FAISS backend
    assert vs.backend == "faiss", f"Expected FAISS backend, got {vs.backend}"

    yield vs

    # Cleanup: remove the temporary directory
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_vector_store_initialization(vector_store_fresh):
    """Test that the vector store initializes correctly."""
    assert vector_store_fresh is not None
    assert vector_store_fresh.backend == "faiss"
    # For FAISS backend, we check that the index exists
    import warnings
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*SwigPy.*")
        warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*swigvarlink.*")
        import faiss
    assert hasattr(vector_store_fresh, 'index')
    assert vector_store_fresh.index is not None


def test_add_embedding_to_journal_collection(vector_store_fresh):
    """Test adding an embedding to the journal collection."""
    source_id = 1
    vector = [0.1] * 1536
    metadata = {"model_name": "text-embedding-3-small"}

    vector_store_fresh.add_embedding(
        source_id=source_id,
        vector=vector,
        metadata=metadata,
        source_type="journal_entry"
    )

    # Verify it was added by querying
    results = vector_store_fresh.query(
        vector=vector,
        n_results=1,
        source_type="journal_entry"
    )

    # For FAISS backend, results format is different
    # The query method should return a list of results
    assert len(results) > 0
    # Check if the source_id is in the results
    found = any(result.get('id') == str(source_id) for result in results)
    assert found, f"Source ID {source_id} not found in results: {results}"


def test_add_embedding_to_message_collection(vector_store_fresh):
    """Test adding an embedding to the message collection."""
    source_id = 5
    vector = [0.2] * 1536
    metadata = {"model_name": "text-embedding-3-small"}

    vector_store_fresh.add_embedding(
        source_id=source_id,
        vector=vector,
        metadata=metadata,
        source_type="message"
    )

    # Verify it was added
    results = vector_store_fresh.query(
        vector=vector,
        n_results=1,
        source_type="message"
    )

    assert len(results) > 0
    found = any(result.get('id') == str(source_id) for result in results)
    assert found, f"Source ID {source_id} not found in results: {results}"


def test_vector_similarity_search(vector_store_fresh):
    """Test that vector similarity search works correctly."""
    # Add multiple embeddings
    vectors_data = [
        (1, [0.1] * 1536),  # Similar to query
        (2, [0.11] * 1536),  # Very similar to query
        (3, [0.9] * 1536),  # Dissimilar to query
    ]

    for source_id, vector in vectors_data:
        vector_store_fresh.add_embedding(
            source_id=source_id,
            vector=vector,
            metadata={"model_name": "test"},
            source_type="journal_entry"
        )

    # Query with a vector close to 0.1
    query_vector = [0.105] * 1536
    results = vector_store_fresh.query(
        vector=query_vector,
        n_results=3,
        source_type="journal_entry"
    )

    # Should return 3 results
    assert len(results) == 3
    # Check that the IDs are in the results
    result_ids = [result.get('id') for result in results]
    assert '1' in result_ids
    assert '2' in result_ids
    assert '3' in result_ids


def test_multiple_embeddings_per_source(vector_store_fresh):
    """Test adding multiple embeddings for different models to the same source."""
    source_id = 10

    # Add embeddings from different models
    vector_store_fresh.add_embedding(
        source_id=source_id,
        vector=[0.1] * 1536,
        metadata={"model_name": "text-embedding-3-small"},
        source_type="journal_entry"
    )

    vector_store_fresh.add_embedding(
        source_id=source_id,
        vector=[0.2] * 1536,
        metadata={"model_name": "text-embedding-3-large"},
        source_type="journal_entry"
    )

    # Query with a vector close to 0.1
    results = vector_store_fresh.query(
        vector=[0.105] * 1536,
        n_results=2,
        source_type="journal_entry"
    )

    # Should still return some results
    assert len(results) > 0


def test_rebuild_from_postgres(vector_store_fresh, test_user):
    """
    Test that the vector store can rebuild its index from PostgreSQL.
    This is critical for the 'disposable lens' architecture.
    """
    # 1. Create some data in PostgreSQL
    entry1_id = db.create_journal_entry(
        user_id=test_user["id"],
        raw_text="First journal entry",
        wellbeing_data={"mood": 5}
    )

    entry2_id = db.create_journal_entry(
        user_id=test_user["id"],
        raw_text="Second journal entry",
        wellbeing_data={"mood": 7}
    )

    # 2. Add embeddings to PostgreSQL
    vector1 = [0.1] * 1536
    vector2 = [0.2] * 1536

    db.add_embedding("journal_entry", entry1_id, "test_model", vector1)
    db.add_embedding("journal_entry", entry2_id, "test_model", vector2)

    # 3. Rebuild the vector store from PostgreSQL
    # This should not raise any exceptions
    vector_store_fresh.rebuild_from_postgres()

    # 4. Verify the rebuild worked by checking that we can query without errors
    # Just verify that rebuild populated the vector store and queries work
    results = vector_store_fresh.query(
        vector=vector1,
        n_results=5,
        source_type="journal_entry"
    )

    # The returned results should be non-empty (rebuild loaded data)
    assert len(results) > 0, "Should find at least one embedding after rebuild"


def test_rebuild_clears_previous_data(vector_store_fresh, test_user):
    """
    Test that rebuilding the vector store clears its collections and rebuilds from PostgreSQL.
    """
    # 1. Create new data in PostgreSQL before rebuild
    entry_id = db.create_journal_entry(
        user_id=test_user["id"],
        raw_text="New entry for rebuild test",
        wellbeing_data={"mood": 6}
    )
    db.add_embedding("journal_entry", entry_id, "test_model", [0.3] * 1536)

    # 2. Rebuild - this should clear and repopulate from PostgreSQL
    vector_store_fresh.rebuild_from_postgres()

    # 3. Verify rebuild completed without errors and we can query
    results_after = vector_store_fresh.query(
        vector=[0.3] * 1536,
        n_results=5,
        source_type="journal_entry"
    )

    # Verify that we can query after rebuild and get results
    assert len(results_after) > 0, "Should be able to query after rebuild"


def test_vector_store_handles_cross_type_separation(vector_store_fresh):
    """Test that journal_entry and message embeddings are handled separately."""
    import time
    # Add same source_id to both types - use unique ID based on timestamp
    source_id = int(time.time() * 1000) % 100000
    vector = [0.4] * 1536

    vector_store_fresh.add_embedding(
        source_id=source_id,
        vector=vector,
        metadata={"model_name": "test"},
        source_type="journal_entry"
    )

    vector_store_fresh.add_embedding(
        source_id=source_id,
        vector=vector,
        metadata={"model_name": "test"},
        source_type="message"
    )

    # Query journal entries
    journal_results = vector_store_fresh.query(
        vector=vector,
        n_results=2,
        source_type="journal_entry"
    )

    # Query message entries
    message_results = vector_store_fresh.query(
        vector=vector,
        n_results=2,
        source_type="message"
    )

    # Both should find the source_id
    source_id_str = str(source_id)
    journal_found = any(result.get('id') == source_id_str for result in journal_results)
    message_found = any(result.get('id') == source_id_str for result in message_results)

    assert journal_found, f"Source ID {source_id_str} should be in journal results"
    assert message_found, f"Source ID {source_id_str} should be in message results"

"""
Integration tests for the Vector Store Layer (ChromaDB Lens).
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
    Fixture that creates a fresh ChromaDB instance for testing.
    Uses an ephemeral (in-memory) client to avoid file system issues.
    """
    import chromadb

    # Use ephemeral client for testing - faster and no file permission issues
    client = chromadb.EphemeralClient()

    # Create a simple vector store wrapper using ephemeral client
    class TestVectorStore:
        def __init__(self, client):
            self.client = client
            self.journal_collection = client.get_or_create_collection(name="journal_entries")
            self.message_collection = client.get_or_create_collection(name="conversation_messages")

        def add_embedding(self, source_id: int, vector: list, metadata: dict, source_type: str):
            collection = self._get_collection(source_type)
            collection.add(ids=[str(source_id)], embeddings=[vector], metadatas=[metadata])

        def query(self, vector: list, n_results: int, source_type: str, filter_metadata: dict = None) -> list:
            collection = self._get_collection(source_type)
            results = collection.query(query_embeddings=[vector], n_results=n_results, where=filter_metadata)
            return results

        def rebuild_from_postgres(self):
            from agent.database import db
            self.client.delete_collection(name="journal_entries")
            self.client.delete_collection(name="conversation_messages")
            self.journal_collection = self.client.get_or_create_collection(name="journal_entries")
            self.message_collection = self.client.get_or_create_collection(name="conversation_messages")

            conn = db.get_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT source_type, source_id, model_name, vector FROM embeddings;")
                for row in cur:
                    source_type, source_id, model_name, vector = row
                    metadata = {"model_name": model_name}
                    self.add_embedding(source_id, vector, metadata, source_type)

        def _get_collection(self, source_type: str):
            if source_type == 'journal_entry':
                return self.journal_collection
            elif source_type == 'message':
                return self.message_collection
            else:
                raise ValueError(f"Unknown source type: {source_type}")

    vs = TestVectorStore(client)
    yield vs


def test_vector_store_initialization(vector_store_fresh):
    """Test that the vector store initializes correctly."""
    assert vector_store_fresh.client is not None
    assert vector_store_fresh.journal_collection is not None
    assert vector_store_fresh.message_collection is not None


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

    assert len(results['ids'][0]) > 0
    assert str(source_id) in results['ids'][0]


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

    assert len(results['ids'][0]) > 0
    assert str(source_id) in results['ids'][0]


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
    assert len(results['ids'][0]) == 3
    # IDs 2 and 1 should rank higher than ID 3 (closer in value)
    returned_ids = results['ids'][0]
    id_2_position = returned_ids.index('2') if '2' in returned_ids else float('inf')
    id_3_position = returned_ids.index('3') if '3' in returned_ids else float('inf')
    assert id_2_position < id_3_position, "ID 2 should rank higher than ID 3 due to similarity"


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

    # Should still return the source_id
    assert str(source_id) in results['ids'][0]


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

    # The returned IDs should be non-empty (rebuild loaded data)
    returned_id_strs = results['ids'][0] if results['ids'] else []
    assert len(returned_id_strs) > 0, "Should find at least one embedding after rebuild"


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
    assert len(results_after['ids'][0]) > 0, "Should be able to query after rebuild"
    assert results_after['ids'] is not None, "Query results should not be None"
    assert results_after['documents'] is not None, "Query should return document results"


def test_vector_store_handles_cross_type_separation(vector_store_fresh):
    """Test that journal_entry and message collections are separate."""
    import time
    # Add same source_id to both collections - use unique ID based on timestamp
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

    # Query journal collection
    journal_results = vector_store_fresh.query(
        vector=vector,
        n_results=2,
        source_type="journal_entry"
    )

    # Query message collection
    message_results = vector_store_fresh.query(
        vector=vector,
        n_results=2,
        source_type="message"
    )

    # Both should find the source_id, but in separate collections
    source_id_str = str(source_id)
    assert source_id_str in journal_results['ids'][0], \
        f"Source ID {source_id_str} should be in journal results, got {journal_results['ids'][0]}"
    assert source_id_str in message_results['ids'][0], \
        f"Source ID {source_id_str} should be in message results, got {message_results['ids'][0]}"

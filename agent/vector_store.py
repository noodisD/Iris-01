"""
Vector Store Layer - ChromaDB Lens

This module acts as a disposable, read-optimized lens for semantic search.
It mirrors embeddings from the PostgreSQL source of truth and is fully rebuildable.
"""

import logging
import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)

class VectorStore:
    """Manages the ChromaDB vector index."""

    def __init__(self, path: str = "data/chroma_db"):
        """
        Initializes the VectorStore.

        Args:
            path: Path to the directory where ChromaDB should store its data.
        """
        logger.info(f"Initializing ChromaDB at path: {path}")
        self.client = chromadb.PersistentClient(path=path)
        
        # In a real application, you would configure the embedding function
        # based on the model used (e.g., OpenAI). For now, we use a default.
        self.embedding_function = embedding_functions.DefaultEmbeddingFunction()

        # Create or get collections for different source types
        self.journal_collection = self.client.get_or_create_collection(
            name="journal_entries",
            embedding_function=self.embedding_function
        )
        self.message_collection = self.client.get_or_create_collection(
            name="conversation_messages",
            embedding_function=self.embedding_function
        )
        logger.info("ChromaDB collections initialized.")

    def add_embedding(self, source_id: int, vector: list, metadata: dict, source_type: str):
        """
        Adds or updates an embedding in the appropriate collection.

        Args:
            source_id: The ID of the source item in PostgreSQL.
            vector: The embedding vector.
            metadata: A dictionary of metadata to store with the embedding.
            source_type: The type of the source ('journal_entry' or 'message').
        """
        collection = self._get_collection(source_type)
        collection.add(
            ids=[str(source_id)],
            embeddings=[vector],
            metadatas=[metadata]
        )

    def query(self, vector: list, n_results: int, source_type: str, filter_metadata: dict = None) -> list:
        """
        Performs a similarity search in the appropriate collection.

        Args:
            vector: The vector to search with.
            n_results: The number of results to return.
            source_type: The type of source to search in.
            filter_metadata: Optional metadata to filter by.

        Returns:
            A list of search results.
        """
        collection = self._get_collection(source_type)
        results = collection.query(
            query_embeddings=[vector],
            n_results=n_results,
            where=filter_metadata
        )
        return results

    def rebuild_from_postgres(self):
        """
        Clears the existing index and rebuilds it from embeddings in PostgreSQL.
        This is a critical function for maintaining the "disposable lens" principle.
        """
        logger.info("Rebuilding ChromaDB index from PostgreSQL source of truth...")
        
        # This needs access to the Database instance.
        # We'll import it here to avoid circular dependencies at the module level.
        from .database import db

        # Clear existing collections
        self.client.delete_collection(name="journal_entries")
        self.client.delete_collection(name="conversation_messages")
        self.journal_collection = self.client.get_or_create_collection(name="journal_entries")
        self.message_collection = self.client.get_or_create_collection(name="conversation_messages")
        logger.info("Cleared existing ChromaDB collections.")

        conn = db.get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT source_type, source_id, model_name, vector FROM embeddings;")
            
            count = 0
            for row in cur:
                source_type, source_id, model_name, vector = row
                metadata = {"model_name": model_name}
                self.add_embedding(source_id, vector, metadata, source_type)
                count += 1
        
        logger.info(f"Successfully rebuilt ChromaDB index with {count} embeddings from PostgreSQL.")

    def _get_collection(self, source_type: str):
        """Helper to get the correct collection based on source type."""
        if source_type == 'journal_entry':
            return self.journal_collection
        elif source_type == 'message':
            return self.message_collection
        else:
            raise ValueError(f"Unknown source type for vector store: {source_type}")


# Global instance
vector_store = VectorStore()

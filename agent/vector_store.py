"""
Vector Store Layer - FAISS-based Lens

This module acts as a disposable, read-optimized lens for semantic search.
It mirrors embeddings from the PostgreSQL source of truth and is fully rebuildable.
"""

import logging
import os
import pickle
import numpy as np
from typing import List, Dict, Any, Optional
from pathlib import Path

# Attempt to import FAISS, a more Python 3.14-compatible vector store
try:
    import warnings
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*SwigPy.*")
        warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*swigvarlink.*")
        import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    faiss = None

# Fallback to ChromaDB if FAISS is not available
try:
    import chromadb
    # Monkeypatch posthog to silence telemetry errors caused by version mismatch
    try:
        import posthog
        def noop(*args, **kwargs): return
        posthog.capture = noop
    except ImportError:
        pass

    from chromadb.config import Settings
    from chromadb.utils import embedding_functions
    from .config import settings

    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    chromadb = None
    Settings = None
    embedding_functions = None
    settings = None

logger = logging.getLogger(__name__)

class VectorStore:
    """Manages the vector index using FAISS or ChromaDB."""

    def __init__(self, path: str = "data/faiss_index"):
        """
        Initializes the VectorStore.

        Args:
            path: Path to the directory where the vector store should store its data.
        """
        if FAISS_AVAILABLE:
            logger.info(f"Initializing FAISS at path: {path}")
            self.backend = "faiss"
            self.path = Path(path)
            self.path.mkdir(parents=True, exist_ok=True)

            # Initialize FAISS index (assuming 1536-dimensional vectors for OpenAI embeddings)
            self.dimension = 1536
            self.index = faiss.IndexFlatIP(self.dimension)  # Inner product for cosine similarity after normalization

            # Store metadata separately
            self.metadata = {}  # Maps index position to metadata
            self.id_to_idx = {}  # Maps source_id to index position
            self.idx_to_id = {}  # Maps index position to source_id

            # Load existing data if available
            self.load_from_disk()

        elif CHROMADB_AVAILABLE:
            logger.info(f"Initializing ChromaDB at path: {path}")
            self.client = chromadb.PersistentClient(
                path=path,
                settings=Settings(anonymized_telemetry=settings.CHROMADB_TELEMETRY)
            )

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
            self.backend = "chromadb"
        else:
            # Fallback to in-memory storage with disk persistence
            logger.warning("Neither FAISS nor ChromaDB is available. Using fallback vector store.")
            self.backend = "fallback"
            self.path = Path(path)
            self.path.mkdir(parents=True, exist_ok=True)

            # Simple in-memory storage with disk persistence
            self.embeddings_storage = {
                "journal_entries": [],
                "conversation_messages": []
            }

            # Load existing data if available
            self.load_from_disk()

    def load_from_disk(self):
        """Load vector store data from disk."""
        try:
            if self.backend == "faiss":
                index_file = self.path / "faiss.index"
                meta_file = self.path / "faiss_meta.pkl"

                if index_file.exists():
                    self.index = faiss.read_index(str(index_file))

                if meta_file.exists():
                    with open(meta_file, 'rb') as f:
                        data = pickle.load(f)
                        self.metadata = data.get('metadata', {})
                        self.id_to_idx = data.get('id_to_idx', {})
                        self.idx_to_id = data.get('idx_to_id', {})

            elif self.backend == "fallback":
                embeddings_file = self.path / "embeddings.pkl"
                if embeddings_file.exists():
                    with open(embeddings_file, 'rb') as f:
                        loaded_data = pickle.load(f)
                        self.embeddings_storage = loaded_data
        except Exception as e:
            logger.warning(f"Could not load vector store from disk: {e}")

    def save_to_disk(self):
        """Save vector store data to disk."""
        try:
            if self.backend == "faiss":
                index_file = self.path / "faiss.index"
                meta_file = self.path / "faiss_meta.pkl"

                faiss.write_index(self.index, str(index_file))

                with open(meta_file, 'wb') as f:
                    pickle.dump({
                        'metadata': self.metadata,
                        'id_to_idx': self.id_to_idx,
                        'idx_to_id': self.idx_to_id
                    }, f)

            elif self.backend == "fallback":
                embeddings_file = self.path / "embeddings.pkl"
                with open(embeddings_file, 'wb') as f:
                    pickle.dump(self.embeddings_storage, f)
        except Exception as e:
            logger.warning(f"Could not save vector store to disk: {e}")

    def add_embedding(self, source_id: int, vector: list, metadata: dict, source_type: str):
        """
        Adds or updates an embedding in the appropriate collection.

        Args:
            source_id: The ID of the source item in PostgreSQL.
            vector: The embedding vector.
            metadata: A dictionary of metadata to store with the embedding.
            source_type: The type of the source ('journal_entry' or 'message').
        """
        if self.backend == "faiss":
            # Normalize the vector for cosine similarity
            vector_np = np.array(vector, dtype=np.float32).reshape(1, -1)
            vector_norm = vector_np / np.linalg.norm(vector_np, axis=1, keepdims=True)

            # Add to FAISS index
            idx = self.index.ntotal
            self.index.add(vector_norm.astype(np.float32))

            # Store mappings
            self.id_to_idx[source_id] = idx
            self.idx_to_id[idx] = source_id
            self.metadata[idx] = metadata

        elif self.backend == "chromadb":
            collection = self._get_collection(source_type)
            collection.add(
                ids=[str(source_id)],
                embeddings=[vector],
                metadatas=[metadata]
            )
        elif self.backend == "fallback":
            logger.warning("FAISS and ChromaDB are not available. Storing in fallback storage.")
            self.embeddings_storage[source_type].append({
                'source_id': source_id,
                'vector': vector,
                'metadata': metadata
            })

        # Persist to disk
        self.save_to_disk()

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
        if self.backend == "faiss":
            # Normalize the query vector
            vector_np = np.array(vector, dtype=np.float32).reshape(1, -1)
            vector_norm = vector_np / np.linalg.norm(vector_np, axis=1, keepdims=True)

            # Perform search
            scores, indices = self.index.search(vector_norm.astype(np.float32), n_results)

            # Format results to match expected format
            results = []
            for i in range(len(indices[0])):
                idx = indices[0][i]
                if idx != -1 and idx in self.idx_to_id:  # -1 indicates no result
                    source_id = self.idx_to_id[idx]
                    result = {
                        'id': str(source_id),
                        'distance': float(scores[0][i]),
                        'metadata': self.metadata.get(idx, {}),
                        'embedding': self.get_embedding_by_id(source_id) if hasattr(self, 'get_embedding_by_id') else None
                    }
                    results.append(result)
            return results

        elif self.backend == "chromadb":
            collection = self._get_collection(source_type)
            results = collection.query(
                query_embeddings=[vector],
                n_results=n_results,
                where=filter_metadata
            )
            return results
        elif self.backend == "fallback":
            logger.warning("FAISS and ChromaDB are not available. Returning empty results for query.")
            return []

        return []

    def rebuild_from_postgres(self):
        """
        Clears the existing index and rebuilds it from embeddings in PostgreSQL.
        This is a critical function for maintaining the "disposable lens" principle.
        """
        if self.backend == "faiss":
            # Reset FAISS index
            self.index.reset()
            self.metadata.clear()
            self.id_to_idx.clear()
            self.idx_to_id.clear()
        elif self.backend == "chromadb":
            # Clear existing collections
            self.client.delete_collection(name="journal_entries")
            self.client.delete_collection(name="conversation_messages")
            self.journal_collection = self.client.get_or_create_collection(name="journal_entries")
            self.message_collection = self.client.get_or_create_collection(name="conversation_messages")
        elif self.backend == "fallback":
            self.embeddings_storage = {
                "journal_entries": [],
                "conversation_messages": []
            }

        logger.info(f"Rebuilding {self.backend.upper()} index from PostgreSQL source of truth...")

        # This needs access to the Database instance.
        # We'll import it here to avoid circular dependencies at the module level.
        from .database import db

        conn = db.get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT source_type, source_id, model_name, vector FROM embeddings;")

            count = 0
            for row in cur:
                source_type, source_id, model_name, vector = row
                metadata = {"model_name": model_name}
                self.add_embedding(source_id, vector, metadata, source_type)
                count += 1

        logger.info(f"Successfully rebuilt {self.backend.upper()} index with {count} embeddings from PostgreSQL.")

    def _get_collection(self, source_type: str):
        """Helper to get the correct collection based on source type."""
        if self.backend != "chromadb":
            logger.warning(f"ChromaDB is not the active backend. Cannot get collection for {self.backend}.")
            return None

        if source_type == 'journal_entry':
            return self.journal_collection
        elif source_type == 'message':
            return self.message_collection
        else:
            raise ValueError(f"Unknown source type for vector store: {source_type}")


# Global instance
vector_store = VectorStore()

"""Memory search compares every memory, not one cluster of them (migration 0052)."""

from __future__ import annotations

import random

from agent.database import db


def test_no_approximate_vector_index_hides_memories():
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT indexname FROM pg_indexes
                        WHERE tablename IN ('embeddings', 'themes')
                          AND (indexdef ILIKE '%ivfflat%' OR indexdef ILIKE '%hnsw%')""")
        assert cur.fetchall() == []


def test_the_nearest_memory_is_always_found(test_user):
    owner = test_user["id"]
    rng = random.Random(3)
    vectors = {}
    for n in range(60):
        reflection_id = db.create_reflection(owner, f"An invented note number {n} about the allotment.")
        vector = [rng.uniform(-1, 1) for _ in range(1536)]
        db.add_embedding("reflection", reflection_id, "text-embedding-3-small", vector)
        vectors[reflection_id] = vector
    for reflection_id, vector in list(vectors.items())[::7]:
        found = db.search_similar_embeddings(owner, vector, n_results=3)
        assert found[0]["source_type"] == "reflection" and found[0]["source_id"] == reflection_id

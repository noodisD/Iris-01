# retrieval.complete

**What it means:** Chat's memory search misses memories an exact search finds.

**Confirm:** Check `pg_indexes` on embeddings for ivfflat or hnsw; compare `search_similar_embeddings` with an exact scan.

**Safe fix:** An approximate index is back: drop it (needs-owner: migration). A filter dropped a memory kind: fix the query.

**Never:** Do not add an approximate index without probes set and this check passing.

See [README](README.md) for action classes and the rules every check follows.

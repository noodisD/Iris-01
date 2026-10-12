-- 0052_exact_vector_search.sql
--
-- Memory search was approximate, and wrong. The IVFFlat indexes from 0001 cut
-- the vectors into 100 (embeddings) and 50 (themes) lists, trained when the
-- tables were almost empty, and a query looks in one list by default
-- (ivfflat.probes = 1): about one memory in a hundred was ever compared. A
-- passage whose own question ranked it first by exact distance was often not
-- returned at all, so chat recalled the wrong things.
--
-- An exact scan of a few thousand vectors takes milliseconds. Without these
-- indexes every search is exact. An approximate index (HNSW) is worth adding
-- back only when the archive reaches hundreds of thousands of vectors.

DROP INDEX IF EXISTS idx_embeddings_vector_cosine;
DROP INDEX IF EXISTS idx_themes_centroid_cosine;

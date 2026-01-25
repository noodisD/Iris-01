-- Setup pgvector extension and indexes for semantic search
-- Run this script on the PostgreSQL database server once during setup

-- Enable pgvector extension (must be run by superuser)
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify embeddings table exists (should already exist from initial schema)
-- This is just documentation of the required schema:
-- CREATE TABLE embeddings (
--     id SERIAL PRIMARY KEY,
--     source_type VARCHAR(50) NOT NULL,
--     source_id INTEGER NOT NULL,
--     model_name VARCHAR(100) NOT NULL,
--     vector VECTOR(1536) NOT NULL,
--     created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
--     UNIQUE(source_type, source_id, model_name)
-- );

-- Create IVFFlat index for fast semantic search
-- This divides the 1536-dim space into 100 clusters, improving query speed ~1000x
-- Trade-off: ~1% accuracy loss (imperceptible for semantic search)
CREATE INDEX IF NOT EXISTS embeddings_vector_ivf ON embeddings
USING ivfflat (vector vector_cosine_ops)
WITH (lists = 100);

-- Create supporting indexes for filtering
CREATE INDEX IF NOT EXISTS embeddings_source_type_idx ON embeddings(source_type);
CREATE INDEX IF NOT EXISTS embeddings_source_id_idx ON embeddings(source_id);
CREATE INDEX IF NOT EXISTS embeddings_created_at_idx ON embeddings(created_at DESC);

-- Analyze the table for query planner optimization
ANALYZE embeddings;

-- Report index status
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'embeddings'
ORDER BY indexname;

-- Optional pgvector migration for local vector search.
--
-- Run this after 001_create_pgvector_schema.sql only on a PostgreSQL server
-- where pgvector is installed. If CREATE EXTENSION vector fails with
-- "extension vector is not available", install pgvector on the server first
-- or keep using chunks.embedding_id with an external vector store.
--
-- MVP embedding dimension: 1536.

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS embedding vector(1536);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE embedding IS NOT NULL;

COMMIT;

-- Semantik marka arama: pgvector ile marka içerik embedding'leri
-- Embedding modeli: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (384 boyut)

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS brand_embeddings (
    brand_id INTEGER PRIMARY KEY REFERENCES brands(id) ON DELETE CASCADE,
    embedding vector(384) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

-- Cosine mesafesi için HNSW index (küçük veri için de zararsız, ileriye dönük)
CREATE INDEX IF NOT EXISTS ix_brand_embeddings_hnsw
    ON brand_embeddings USING hnsw (embedding vector_cosine_ops);

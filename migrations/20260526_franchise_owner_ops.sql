-- Franchise outlets + owner documents (training / SOP)

DO $body$
BEGIN
    CREATE TYPE outlet_status AS ENUM ('active', 'inactive', 'planned');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$body$;

DO $body$
BEGIN
    CREATE TYPE owner_document_type AS ENUM ('training', 'sop', 'other');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$body$;

CREATE TABLE IF NOT EXISTS franchise_outlets (
    id SERIAL PRIMARY KEY,
    franchise_owner_id INTEGER NOT NULL REFERENCES franchise_owners(id) ON DELETE CASCADE,
    brand_id INTEGER REFERENCES brands(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    city VARCHAR(120) NOT NULL,
    address TEXT,
    status outlet_status NOT NULL DEFAULT 'active',
    opened_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_franchise_outlets_owner_id ON franchise_outlets (franchise_owner_id);

CREATE TABLE IF NOT EXISTS franchise_owner_documents (
    id SERIAL PRIMARY KEY,
    franchise_owner_id INTEGER NOT NULL REFERENCES franchise_owners(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    document_type owner_document_type NOT NULL DEFAULT 'other',
    file_path VARCHAR(512) NOT NULL,
    mime_type VARCHAR(128) NOT NULL,
    file_size_bytes INTEGER,
    original_filename VARCHAR(255),
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_franchise_owner_documents_owner_id ON franchise_owner_documents (franchise_owner_id);

-- Supply requests: zaman serisi icin
ALTER TABLE supply_requests ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW();

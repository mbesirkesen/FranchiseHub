-- Brand discovery: media, FDD documents, territories

DO $body$
BEGIN
    CREATE TYPE brand_media_type AS ENUM ('logo', 'gallery');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$body$;

DO $body$
BEGIN
    CREATE TYPE territory_status AS ENUM ('available', 'reserved');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$body$;

CREATE TABLE IF NOT EXISTS brand_media (
    id SERIAL PRIMARY KEY,
    brand_id INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    media_type brand_media_type NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    mime_type VARCHAR(128) NOT NULL,
    original_filename VARCHAR(255),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_brand_media_brand_id ON brand_media (brand_id);

CREATE TABLE IF NOT EXISTS brand_fdd_documents (
    id SERIAL PRIMARY KEY,
    brand_id INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    version VARCHAR(64),
    file_path VARCHAR(512) NOT NULL,
    mime_type VARCHAR(128) NOT NULL DEFAULT 'application/pdf',
    file_size_bytes INTEGER,
    published_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_brand_fdd_brand_id ON brand_fdd_documents (brand_id);

CREATE TABLE IF NOT EXISTS brand_territories (
    id SERIAL PRIMARY KEY,
    brand_id INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    region_code VARCHAR(64),
    status territory_status NOT NULL DEFAULT 'available',
    notes TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_brand_territories_brand_id ON brand_territories (brand_id);

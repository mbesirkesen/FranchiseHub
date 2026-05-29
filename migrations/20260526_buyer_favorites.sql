-- Buyer favorite brands

CREATE TABLE IF NOT EXISTS buyer_favorites (
    id SERIAL PRIMARY KEY,
    buyer_id INTEGER NOT NULL REFERENCES buyers(id) ON DELETE CASCADE,
    brand_id INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (buyer_id, brand_id)
);

CREATE INDEX IF NOT EXISTS ix_buyer_favorites_buyer_id ON buyer_favorites (buyer_id);
CREATE INDEX IF NOT EXISTS ix_buyer_favorites_brand_id ON buyer_favorites (brand_id);

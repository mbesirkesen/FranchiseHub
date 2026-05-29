-- Inventory per-outlet + low stock; supply request shipped status

ALTER TABLE inventories ADD COLUMN IF NOT EXISTS outlet_id INTEGER REFERENCES franchise_outlets(id) ON DELETE SET NULL;
ALTER TABLE inventories ADD COLUMN IF NOT EXISTS low_stock_threshold INTEGER NOT NULL DEFAULT 10;

CREATE INDEX IF NOT EXISTS ix_inventories_outlet_id ON inventories (outlet_id);

DO $body$
BEGIN
    ALTER TYPE supply_request_status ADD VALUE 'shipped';
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$body$;

ALTER TABLE supply_requests ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE supply_requests ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW();

CREATE TABLE IF NOT EXISTS inventory_transfers (
    id SERIAL PRIMARY KEY,
    franchise_owner_id INTEGER NOT NULL REFERENCES franchise_owners(id) ON DELETE CASCADE,
    from_outlet_id INTEGER REFERENCES franchise_outlets(id) ON DELETE SET NULL,
    to_outlet_id INTEGER REFERENCES franchise_outlets(id) ON DELETE SET NULL,
    inventory_id INTEGER NOT NULL REFERENCES inventories(id) ON DELETE CASCADE,
    item_name VARCHAR(255) NOT NULL,
    quantity INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_inventory_transfers_owner_id ON inventory_transfers (franchise_owner_id);

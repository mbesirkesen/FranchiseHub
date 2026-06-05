-- Bayi talepleri: hangi şubeden geldiği ve hangi alıcı gönderdiği

ALTER TABLE supply_requests ADD COLUMN IF NOT EXISTS outlet_id INTEGER REFERENCES franchise_outlets(id) ON DELETE SET NULL;
ALTER TABLE supply_requests ADD COLUMN IF NOT EXISTS buyer_id INTEGER REFERENCES buyers(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_supply_requests_outlet_id ON supply_requests (outlet_id);
CREATE INDEX IF NOT EXISTS ix_supply_requests_buyer_id ON supply_requests (buyer_id);

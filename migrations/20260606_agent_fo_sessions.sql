-- Franchise owner asistan oturumları (buyer veya FO — biri dolu)

ALTER TABLE agent_sessions ALTER COLUMN buyer_id DROP NOT NULL;

ALTER TABLE agent_sessions
    ADD COLUMN IF NOT EXISTS franchise_owner_id INTEGER REFERENCES franchise_owners(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS ix_agent_sessions_fo
    ON agent_sessions (franchise_owner_id, updated_at DESC);

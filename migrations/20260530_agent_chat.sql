-- Franchise asistanı: sohbet oturumları ve mesaj geçmişi

CREATE TABLE IF NOT EXISTS agent_sessions (
    id SERIAL PRIMARY KEY,
    buyer_id INTEGER NOT NULL REFERENCES buyers(id) ON DELETE CASCADE,
    title VARCHAR(200),
    brand_context_id INTEGER REFERENCES brands(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_agent_sessions_buyer ON agent_sessions (buyer_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS agent_messages (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    intent VARCHAR(64),
    source VARCHAR(16) NOT NULL DEFAULT 'rules',
    filters_applied JSONB,
    related_brand_ids JSONB,
    latency_ms INTEGER,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_agent_messages_role CHECK (role IN ('user', 'assistant'))
);

CREATE INDEX IF NOT EXISTS ix_agent_messages_session ON agent_messages (session_id, created_at ASC);

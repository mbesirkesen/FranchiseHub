-- Admin: sectors dictionary + audit logs

CREATE TABLE IF NOT EXISTS sectors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL UNIQUE,
    slug VARCHAR(120) UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    actor_role user_role NOT NULL,
    actor_id INTEGER NOT NULL,
    actor_email VARCHAR(255) NOT NULL,
    action VARCHAR(120) NOT NULL,
    resource_type VARCHAR(64) NOT NULL,
    resource_id INTEGER,
    details TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_logs_actor ON audit_logs (actor_role, actor_id);

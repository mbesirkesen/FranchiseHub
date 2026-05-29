-- Auth tokens + email_verified. Idempotent where PostgreSQL allows.
-- Run: psql "$DATABASE_URL" -f migrations/20260526_auth_tokens_and_email_verified.sql

ALTER TABLE buyers ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE franchise_owners ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE admins ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE;

-- auth_token_type: skip if already created (re-run safe)
DO $body$
BEGIN
    CREATE TYPE auth_token_type AS ENUM ('password_reset', 'email_verify', 'refresh');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$body$;

CREATE TABLE IF NOT EXISTS auth_tokens (
    id SERIAL PRIMARY KEY,
    token_type auth_token_type NOT NULL,
    token_hash VARCHAR(64) NOT NULL,
    role user_role NOT NULL,
    subject_id INTEGER NOT NULL,
    email VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    used_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_auth_tokens_token_hash ON auth_tokens (token_hash);
CREATE INDEX IF NOT EXISTS ix_auth_tokens_email_type ON auth_tokens (email, token_type);
CREATE INDEX IF NOT EXISTS ix_auth_tokens_role_subject ON auth_tokens (role, subject_id);

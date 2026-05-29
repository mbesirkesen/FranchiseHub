-- Per-user message read tracking

CREATE TABLE IF NOT EXISTS message_read_receipts (
    id SERIAL PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    reader_role user_role NOT NULL,
    reader_id INTEGER NOT NULL,
    read_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (message_id, reader_role, reader_id)
);

CREATE INDEX IF NOT EXISTS ix_message_read_receipts_message_id ON message_read_receipts (message_id);
CREATE INDEX IF NOT EXISTS ix_message_read_receipts_reader ON message_read_receipts (reader_role, reader_id);

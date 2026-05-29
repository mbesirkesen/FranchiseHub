-- General-purpose uploaded files

CREATE TABLE IF NOT EXISTS uploaded_files (
    id SERIAL PRIMARY KEY,
    uploader_role user_role NOT NULL,
    uploader_id INTEGER NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    mime_type VARCHAR(128) NOT NULL,
    original_filename VARCHAR(255),
    file_size_bytes INTEGER,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_uploaded_files_uploader ON uploaded_files (uploader_role, uploader_id);

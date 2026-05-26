-- applications.created_at (Next.js sozlesmesi / Application tipi)
ALTER TABLE applications
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW();

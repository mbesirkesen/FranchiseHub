-- Admin rolunu ve admin-only tablolari kaldir (idempotent).
-- Calistirma: psql "$DATABASE_URL" -f migrations/20260529_remove_admin.sql

DELETE FROM auth_tokens WHERE role = 'admin';
DELETE FROM message_read_receipts WHERE reader_role = 'admin';
DELETE FROM notifications WHERE recipient_role = 'admin';
DELETE FROM messages WHERE sender_role = 'admin';

DO $$
BEGIN
  IF to_regclass('public.push_devices') IS NOT NULL THEN
    DELETE FROM push_devices WHERE recipient_role = 'admin';
  END IF;
  IF to_regclass('public.uploaded_files') IS NOT NULL THEN
    DELETE FROM uploaded_files WHERE uploader_role = 'admin';
  END IF;
END $$;

DROP TABLE IF EXISTS admins CASCADE;
DROP TABLE IF EXISTS audit_logs CASCADE;
DROP TABLE IF EXISTS sectors CASCADE;

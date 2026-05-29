-- In-app notifications + push device tokens (FCM/APNs)

DO $body$
BEGIN
    CREATE TYPE device_platform AS ENUM ('ios', 'android', 'web');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$body$;

CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    recipient_role user_role NOT NULL,
    recipient_id INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    notification_type VARCHAR(64) NOT NULL DEFAULT 'general',
    action_url VARCHAR(512),
    resource_type VARCHAR(64),
    resource_id INTEGER,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    read_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_notifications_recipient ON notifications (recipient_role, recipient_id);
CREATE INDEX IF NOT EXISTS ix_notifications_unread ON notifications (recipient_role, recipient_id, is_read);

CREATE TABLE IF NOT EXISTS push_devices (
    id SERIAL PRIMARY KEY,
    recipient_role user_role NOT NULL,
    recipient_id INTEGER NOT NULL,
    token VARCHAR(512) NOT NULL,
    platform device_platform NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (recipient_role, recipient_id, token)
);

CREATE INDEX IF NOT EXISTS ix_push_devices_token ON push_devices (token);

-- Migration 0006: Subscription attachments
-- Gives subscriptions the same attachment capability insurances already
-- have (e.g. a signup confirmation or renewal letter).

CREATE TABLE IF NOT EXISTS subscription_attachments (
    id              TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    subscription_id TEXT    NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    filename        TEXT    NOT NULL,
    content_type    TEXT    NOT NULL,
    size_bytes      INTEGER NOT NULL,
    storage_path    TEXT    NOT NULL,
    uploaded_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_subscription_attachments_subscription_id
    ON subscription_attachments(subscription_id);

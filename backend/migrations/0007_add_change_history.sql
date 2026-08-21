-- Migration 0007: Change history
-- Per-record audit trail of field-level edits (who changed what, from/to).

CREATE TABLE IF NOT EXISTS subscription_history (
    id                  TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    subscription_id     TEXT    NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    field               TEXT    NOT NULL,
    old_value           TEXT,
    new_value           TEXT,
    changed_by_user_id  TEXT,
    changed_by_username TEXT    NOT NULL,
    changed_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_subscription_history_subscription_id
    ON subscription_history(subscription_id);

CREATE TABLE IF NOT EXISTS insurance_history (
    id                  TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    insurance_id        TEXT    NOT NULL REFERENCES insurances(id) ON DELETE CASCADE,
    field               TEXT    NOT NULL,
    old_value           TEXT,
    new_value           TEXT,
    changed_by_user_id  TEXT,
    changed_by_username TEXT    NOT NULL,
    changed_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_insurance_history_insurance_id
    ON insurance_history(insurance_id);

-- Migration 0004: Insurances
-- Adds insurance policy tracking, scoped to buckets like subscriptions,
-- with support for uploaded attachments (e.g. policy conditions documents).

CREATE TABLE IF NOT EXISTS insurances (
    id                 TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    bucket_id          TEXT    NOT NULL REFERENCES buckets(id) ON DELETE CASCADE,
    name               TEXT    NOT NULL,
    insurer            TEXT    NOT NULL,
    policy_number      TEXT,
    recurring_interval TEXT    NOT NULL
                       CHECK(recurring_interval IN
                             ('daily','weekly','monthly','quarterly','half-year','yearly')),
    recurring_date     TEXT,           -- ISO-8601 date of the last payment
    end_date           TEXT,
    amount             REAL    NOT NULL DEFAULT 0,
    currency           TEXT    NOT NULL DEFAULT 'EUR',
    category_id        INTEGER REFERENCES categories(id),
    notes              TEXT,
    created_at         TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_insurances_bucket_id ON insurances(bucket_id);

CREATE TRIGGER IF NOT EXISTS insurances_updated_at
AFTER UPDATE ON insurances
FOR EACH ROW
BEGIN
    UPDATE insurances SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- Uploaded documents (e.g. policy conditions PDF) attached to an insurance.
-- The actual file bytes are stored on disk (under the same volume as the
-- SQLite DB); this table only tracks metadata + the storage path.
CREATE TABLE IF NOT EXISTS insurance_attachments (
    id            TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    insurance_id  TEXT    NOT NULL REFERENCES insurances(id) ON DELETE CASCADE,
    filename      TEXT    NOT NULL,
    content_type  TEXT    NOT NULL,
    size_bytes    INTEGER NOT NULL,
    storage_path  TEXT    NOT NULL,
    uploaded_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_insurance_attachments_insurance_id
    ON insurance_attachments(insurance_id);

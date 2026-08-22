-- Migration 0008: Owners
-- Bucket-scoped master data (a person's name) assignable to subscriptions
-- and insurances, e.g. "who in the household this belongs to".

CREATE TABLE IF NOT EXISTS owners (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket_id TEXT NOT NULL REFERENCES buckets(id) ON DELETE CASCADE,
    name      TEXT NOT NULL,
    UNIQUE(bucket_id, name)
);

CREATE INDEX IF NOT EXISTS idx_owners_bucket_id ON owners(bucket_id);

ALTER TABLE subscriptions ADD COLUMN owner_id INTEGER REFERENCES owners(id) ON DELETE SET NULL;
ALTER TABLE insurances ADD COLUMN owner_id INTEGER REFERENCES owners(id) ON DELETE SET NULL;

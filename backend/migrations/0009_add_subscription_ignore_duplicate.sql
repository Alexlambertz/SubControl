-- Migration 0009: Ignore-duplicate flag
-- Replaces the browser-localStorage "marked unique" hack for duplicate
-- detection with a real, server-persisted, per-subscription flag — so the
-- decision survives clearing browser data and is shared across devices
-- and users of the same bucket.

ALTER TABLE subscriptions ADD COLUMN ignore_duplicate INTEGER NOT NULL DEFAULT 0;

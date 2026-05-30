-- Migration 0001: Initial schema
-- Creates all core tables for SubControl.

-- Buckets: authorization scope; users are assigned to buckets.
CREATE TABLE IF NOT EXISTS buckets (
    id         TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name       TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Users: application users, sourced from OIDC.
CREATE TABLE IF NOT EXISTS users (
    id         TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    username   TEXT    NOT NULL UNIQUE,
    last_login TEXT,
    is_admin   INTEGER NOT NULL DEFAULT 0,  -- 1 = admin, 0 = regular user
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Many-to-many: user ↔ bucket membership.
CREATE TABLE IF NOT EXISTS user_buckets (
    user_id   TEXT NOT NULL REFERENCES users(id)   ON DELETE CASCADE,
    bucket_id TEXT NOT NULL REFERENCES buckets(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, bucket_id)
);

-- Providers: normalised list of subscription providers (e.g. Netflix, Spotify).
CREATE TABLE IF NOT EXISTS providers (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT    NOT NULL UNIQUE
);

-- Categories: user-defined groupings (e.g. Streaming, Haushalt).
CREATE TABLE IF NOT EXISTS categories (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT    NOT NULL UNIQUE
);

-- Subscriptions: the core entity.
CREATE TABLE IF NOT EXISTS subscriptions (
    id                 TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    bucket_id          TEXT    NOT NULL REFERENCES buckets(id) ON DELETE CASCADE,
    name               TEXT    NOT NULL,
    provider_id        INTEGER REFERENCES providers(id),
    recurring_interval TEXT    NOT NULL
                       CHECK(recurring_interval IN
                             ('daily','weekly','monthly','quarterly','half-year','yearly')),
    recurring_date     TEXT,           -- ISO-8601 date of the last payment
    amount             REAL    NOT NULL DEFAULT 0,
    currency           TEXT    NOT NULL DEFAULT 'EUR',
    image_url          TEXT,           -- auto-fetched logo URL
    category_id        INTEGER REFERENCES categories(id),
    created_at         TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Trigger: automatically update `updated_at` on subscription changes.
CREATE TRIGGER IF NOT EXISTS subscriptions_updated_at
AFTER UPDATE ON subscriptions
FOR EACH ROW
BEGIN
    UPDATE subscriptions SET updated_at = datetime('now') WHERE id = NEW.id;
END;

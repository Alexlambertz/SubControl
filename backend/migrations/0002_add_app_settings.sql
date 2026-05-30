-- Migration 0002: Application settings table
-- Stores configurable runtime settings (e.g. AI endpoint, model, API key).

CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Seed default AI settings (empty values; configured by admin via UI).
INSERT OR IGNORE INTO app_settings (key, value) VALUES ('ai_api_url',  '');
INSERT OR IGNORE INTO app_settings (key, value) VALUES ('ai_api_key',  '');
INSERT OR IGNORE INTO app_settings (key, value) VALUES ('ai_model',    '');

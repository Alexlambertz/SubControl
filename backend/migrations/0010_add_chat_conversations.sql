-- Migration 0010: Chat conversations
-- Persists AI Chat conversations per user so they can be listed and reopened.

CREATE TABLE IF NOT EXISTS chat_conversations (
    id         TEXT NOT NULL PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      TEXT NOT NULL DEFAULT 'New conversation',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_chat_conversations_user_id ON chat_conversations(user_id);

CREATE TABLE IF NOT EXISTS chat_messages (
    id              TEXT NOT NULL PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    conversation_id TEXT NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_id ON chat_messages(conversation_id);

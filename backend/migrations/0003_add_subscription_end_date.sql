-- Migration 0003: Add end_date to subscriptions
-- Optional ISO-8601 date at which the subscription ceases billing.
-- NULL means the subscription runs indefinitely.
ALTER TABLE subscriptions ADD COLUMN end_date TEXT;

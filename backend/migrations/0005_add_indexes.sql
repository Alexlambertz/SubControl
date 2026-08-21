-- Migration 0005: Indexes
-- subscriptions.bucket_id is the primary filter column for nearly every
-- query in the app; provider_id/category_id are used in every LEFT JOIN.
-- None of these existed before, forcing full table scans as the table grows.

CREATE INDEX IF NOT EXISTS idx_subscriptions_bucket_id ON subscriptions(bucket_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_provider_id ON subscriptions(provider_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_category_id ON subscriptions(category_id);

-- Reverse lookup (bucket -> users) used e.g. on bucket deletion; the
-- existing PRIMARY KEY (user_id, bucket_id) only covers user-first lookups.
CREATE INDEX IF NOT EXISTS idx_user_buckets_bucket_id ON user_buckets(bucket_id);

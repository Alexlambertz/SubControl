# Data Model

## Entity Relationship

```
buckets ──< subscriptions >── providers
   │              │
   │              └── categories
   │
user_buckets >── users
```

## Tables

### `buckets`
| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID hex |
| name | TEXT UNIQUE NOT NULL | |
| created_at | TEXT | datetime('now') |

### `users`
| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID hex |
| username | TEXT UNIQUE NOT NULL | from OIDC `sub` |
| last_login | TEXT | ISO datetime |
| is_admin | INTEGER | 0 or 1 |
| created_at | TEXT | |

### `user_buckets`
Join table: `(user_id, bucket_id)` composite PK. Cascades on delete.

### `providers`
| Column | Type |
|--------|------|
| id | INTEGER PK AUTOINCREMENT |
| name | TEXT UNIQUE NOT NULL |

### `categories`
| Column | Type |
|--------|------|
| id | INTEGER PK AUTOINCREMENT |
| name | TEXT UNIQUE NOT NULL |

### `subscriptions`
| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID hex |
| bucket_id | TEXT FK → buckets | CASCADE on delete |
| name | TEXT NOT NULL | Display name |
| provider_id | INTEGER FK → providers | Nullable |
| recurring_interval | TEXT CHECK | `daily`, `weekly`, `monthly`, `quarterly`, `half-year`, `yearly` |
| recurring_date | TEXT | ISO date, last payment date |
| amount | REAL NOT NULL | The price charged per interval |
| currency | TEXT DEFAULT 'EUR' | 3-char ISO 4217 |
| image_url | TEXT | Logo URL (fetched async) |
| category_id | INTEGER FK → categories | Nullable |
| created_at | TEXT | |
| updated_at | TEXT | Auto-updated by trigger |

### `app_settings`
| Column | Type |
|--------|------|
| key | TEXT PK |
| value | TEXT NOT NULL |
| updated_at | TEXT |

Default keys seeded by migration 0002: `ai_api_url`, `ai_api_key`, `ai_model`.

### `schema_version`
| Column | Type |
|--------|------|
| version | INTEGER PK |
| applied_at | TEXT |

Used by the migration runner to track which SQL files have been applied.

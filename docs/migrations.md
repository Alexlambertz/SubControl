# Migrations

SubControl uses a simple custom migration runner (no Alembic). Migration files are SQL scripts in `backend/migrations/`.

## File naming

```
NNNN_description.sql
```

Examples: `0001_initial_schema.sql`, `0002_add_app_settings.sql`

`NNNN` is a zero-padded integer. The runner applies all files whose `NNNN > current_version` in ascending order.

## Runner behaviour (`backend/migrations/runner.py`)

1. Opens (or creates) the SQLite database.
2. Bootstraps a `schema_version` table if it doesn't exist.
3. Reads `MAX(version)` — defaults to 0.
4. Scans `migrations/` for `NNNN_*.sql` files with `NNNN > current_version`.
5. Applies each in a transaction.
6. Inserts a `schema_version` row on success.
7. On failure: rolls back and raises `RuntimeError` — the app refuses to start.

## Adding a migration

1. Create `backend/migrations/NNNN_description.sql` with the next sequential number.
2. Write idempotent SQL (use `IF NOT EXISTS`, `INSERT OR IGNORE`, etc.).
3. The migration runs automatically on the next app start.

## Current migrations

| Version | File | Description |
|---------|------|-------------|
| 1 | `0001_initial_schema.sql` | Full initial schema: all tables + updated_at trigger |
| 2 | `0002_add_app_settings.sql` | `app_settings` table + seed AI config keys |

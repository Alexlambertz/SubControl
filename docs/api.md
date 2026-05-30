# API Reference

All routes are prefixed `/api`. Interactive docs available at `/api/docs` (Swagger UI) and `/api/redoc`.

## System

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/health` | None | Liveness probe; returns `{status, version}` |

## Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/auth/me` | Yes | Current user profile |
| POST | `/api/auth/login` | OIDC token | Upsert user, set last_login, promote first user to admin |

## Buckets

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/buckets` | Yes | List buckets |
| POST | `/api/buckets` | Yes | Create bucket |
| GET | `/api/buckets/{id}` | Yes | Get bucket |
| PUT | `/api/buckets/{id}` | Yes | Rename bucket |
| DELETE | `/api/buckets/{id}` | Admin | Delete bucket (cascades subscriptions) |
| POST | `/api/buckets/{id}/users/{uid}` | Admin | Assign user to bucket |
| DELETE | `/api/buckets/{id}/users/{uid}` | Admin | Remove user from bucket |

## Users

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/users` | Admin | List all users |
| GET | `/api/users/{id}` | Admin | Get user |
| DELETE | `/api/users/{id}` | Admin | Delete user |

## Subscriptions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/buckets/{id}/subscriptions` | Yes | List subscriptions in bucket |
| POST | `/api/buckets/{id}/subscriptions` | Yes | Create subscription |
| GET | `/api/buckets/{id}/subscriptions/{sid}` | Yes | Get subscription |
| PUT | `/api/buckets/{id}/subscriptions/{sid}` | Yes | Update subscription |
| DELETE | `/api/buckets/{id}/subscriptions/{sid}` | Yes | Delete subscription |
| POST | `/api/buckets/{id}/subscriptions/import` | Yes | CSV bulk import |

## Providers & Categories

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/providers` | Yes | List providers |
| POST | `/api/providers` | Yes | Create provider |
| GET | `/api/categories` | Yes | List categories |
| POST | `/api/categories` | Yes | Create category |

## Dashboard

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/dashboard` | Yes | Summary; params: `mode`, `month`, `bucket_id`, `category_id` |

## Settings

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/settings` | Admin | Get all settings |
| GET | `/api/settings/{key}` | Admin | Get single setting |
| PUT | `/api/settings/{key}` | Admin | Upsert setting |

## Chat

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/chat/message` | Yes | Send message; SSE streaming response |

## Search

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/search?q=…` | Yes | Global search across subscriptions |

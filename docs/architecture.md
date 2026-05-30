# Architecture

SubControl is a full-stack subscription management application with a clear three-tier architecture.

## Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Browser / SPA                         │
│         React 19 + TypeScript + Vite + Tailwind          │
│   (Dashboard, Buckets, Subscriptions, Chat, Settings)    │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP / SSE  (/api/*)
┌─────────────────────▼───────────────────────────────────┐
│                  FastAPI Backend                          │
│          Python 3.12 + aiosqlite + pydantic              │
│   (REST routers, services, migrations, auth middleware)  │
└──────────────┬──────────────────────────────────────────┘
               │ aiosqlite
┌──────────────▼──────────────────────────────────────────┐
│              SQLite Database                             │
│  (buckets, users, subscriptions, providers, categories,  │
│   app_settings, schema_version)                          │
└─────────────────────────────────────────────────────────┘

           Optional stdio companion process:
┌─────────────────────────────────────────────────────────┐
│                    MCP Server                            │
│         7 tools via HTTP → FastAPI backend               │
└─────────────────────────────────────────────────────────┘
```

## Backend

- **FastAPI** application factory pattern (`create_app()`)
- **Lifespan** hook: runs migrations on startup, then serves requests
- **aiosqlite**: all DB I/O is async; connections yielded per-request via `get_db()` dependency
- **Pydantic v2** for request/response validation
- **pydantic-settings** for `.env` and environment variable configuration
- **Modular routers**: one file per resource group, all prefixed under `/api`
- **Services layer**: logic separated from HTTP concerns (`dashboard.py`, `ai_chat.py`, `logo_fetch.py`, `csv_import.py`)

## Frontend

- **Vite** build tooling with React plugin and Tailwind v4 plugin
- **React Router v6** with `createBrowserRouter`
- **@tanstack/react-query** for all server state
- **AuthContext** (OIDC) — dev mode injects dummy user, production uses Keycloak PKCE
- API layer: `src/api/` typed fetch wrappers, one file per resource

## Auth

Dev mode (`DEV_MODE=true`): no auth, dummy admin user injected.
Production: OIDC PKCE with Keycloak; JWT validated in `dependencies.py`.

## Data persistence

Single SQLite file at `DATABASE_URL` (default `./subcontrol.db`). Versioned migrations in `backend/migrations/` applied at startup by `runner.py`.

## Deployment

Multi-stage Docker build: Node builds the SPA, Python image serves both API and SPA static files on port 8000.

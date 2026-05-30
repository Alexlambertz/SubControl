# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend
```bash
# Install (from project root)
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"

# Run dev server
DEV_MODE=true uvicorn backend.main:app --reload --port 8000

# Run tests (from project root)
backend/.venv/bin/pytest backend/tests/ -v

# Run single test file
backend/.venv/bin/pytest backend/tests/test_subscriptions.py -v

# Run single test
backend/.venv/bin/pytest backend/tests/test_subscriptions.py::TestCreateSubscription::test_create_returns_201 -v
```

### Frontend
```bash
cd frontend
npm install
npm run dev          # Vite dev server → http://localhost:5173
npm run build        # TypeScript check + production build
npm test             # Vitest unit tests (run once)
npm run test:watch   # Vitest in watch mode
npm run test:e2e     # Playwright E2E (requires both servers running)
```

### Docker
```bash
docker compose up -d                     # Production
docker compose --profile oidc up -d      # With Keycloak
docker build -t subcontrol .             # Build image
```

## Architecture

```
SubControl/
├── backend/          FastAPI app + aiosqlite + services
│   ├── main.py       App factory (create_app), router registration
│   ├── config.py     pydantic-settings (.env)
│   ├── database.py   get_db() dependency — re-derives DB path on each call
│   ├── dependencies.py  get_current_user, require_admin
│   ├── migrations/   NNNN_*.sql + runner.py (applied at startup)
│   ├── routers/      One file per resource (auth, buckets, users, subscriptions,
│   │                 dashboard, import_csv, settings, chat, providers_categories)
│   ├── services/     logo_fetch.py, dashboard.py, csv_import.py, ai_chat.py
│   └── tests/        95 tests — conftest.py + test_*.py
├── mcp_server/       Stdio MCP server (7 tools via HTTP → backend)
├── frontend/
│   ├── src/
│   │   ├── api/      Typed fetch wrappers per resource
│   │   ├── auth/     AuthContext.tsx (oidc-client-ts)
│   │   ├── components/  Layout, SortableTable, CurrencyDisplay, etc.
│   │   ├── pages/    Dashboard, Buckets/, Subscriptions/, Chat, Settings, Users
│   │   ├── types/    TypeScript interfaces mirroring Pydantic schemas
│   │   ├── __tests__/  Vitest unit tests
│   │   └── e2e/      Playwright E2E specs
│   ├── vite.config.ts    (proxies /api → :8000; NO test config here)
│   └── vitest.config.ts  (separate, jsdom environment)
├── docs/             Architecture, API, data-model, auth, migrations, etc.
├── Dockerfile        Multi-stage: Node build → Python serve
└── docker-compose.yml
```

## Key patterns

### Test isolation (critical)
Tests patch `cfg.settings.database_url` directly — NOT environment variables — before creating the app:
```python
from backend import config as cfg
cfg.settings.database_url = f"sqlite+aiosqlite:///{test_db_path}"
app = create_app()
```
`get_db()` re-derives the DB path on every call (not a module-level constant).

### Auth in tests
Toggle production mode: `monkeypatch.setattr(cfg.settings, "dev_mode", False)` — **not** `importlib.reload`.

### Router order
`import_csv.router` must be registered **before** `subscriptions.router` in `main.py` — the `/import` path would otherwise be shadowed by `/{sub_id}`.

### Tailwind v4
Uses `@import "tailwindcss"` in `src/index.css` and `@tailwindcss/vite` plugin. No `tailwind.config.js`.

### DEV_MODE
When `true`: dummy admin user injected, all auth bypassed. The `_DEV_USER` id is `"00000000000000000000000000000001"`.

## Data model summary

`buckets` → (many) `subscriptions` → (optional) `providers` / `categories`  
`users` ↔ (many-to-many) `buckets` via `user_buckets`  
`app_settings` — AI config (ai_api_url, ai_api_key, ai_model)  
`schema_version` — migration tracking

Recurring intervals: `daily`, `weekly`, `monthly`, `quarterly`, `half-year`, `yearly`

## Dashboard logic

- **Average monthly**: converts amount using fixed factors (daily×30, weekly×4.33, quarterly÷3, half-year÷6, yearly÷12)
- **Real monthly**: uses `recurring_date` + `python-dateutil relativedelta` to find next due date; only includes subscriptions due in the queried month

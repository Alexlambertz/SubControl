# SubControl

A self-hosted subscription management web application. Track all your recurring subscriptions across multiple "buckets" (e.g. personal, work), visualise monthly spend, import from CSV, and chat with an AI assistant about your costs.

## Features

- **Subscription tracking** — name, provider, amount, currency, billing interval, payment date
- **Buckets** — group subscriptions (personal, work, family, etc.)
- **Dashboard** — average monthly spend and real monthly spend by category (bar chart)
- **CSV import** — bulk import with per-row error reporting
- **Logo fetching** — automatic provider logos via Clearbit / Google Favicons
- **AI Chat** — ask about your subscriptions; AI can create/update them for you (OpenAI-compatible, bring your own key)
- **MCP server** — expose subscriptions as tools to Claude Desktop or any MCP-compatible agent
- **Auth** — dev mode (no auth) or production Keycloak OIDC with first-user admin promotion

## Quick start

```bash
# 1. Clone
git clone https://github.com/youruser/subcontrol.git
cd SubControl

# 2. Configure
cp .env.example .env
# Edit .env for production; for local dev the defaults work as-is

# 3. Run with Docker
docker compose up -d

# App is now at http://localhost:8000
```

## Development setup

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
DEV_MODE=true uvicorn backend.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev        # → http://localhost:5173 (proxies /api to :8000)
```

### Tests

```bash
# Backend (from project root)
backend/.venv/bin/pytest backend/tests/ -v

# Frontend unit tests
cd frontend && npm test

# E2E (requires both servers running)
cd frontend && npm run test:e2e
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEV_MODE` | `true` | Skip OIDC auth — for local dev only |
| `DATABASE_URL` | `sqlite+aiosqlite:///./subcontrol.db` | SQLite connection string |
| `SECRET_KEY` | `dev-secret` | JWT signing key (change in production) |
| `OIDC_ISSUER_URL` | — | Keycloak realm URL |
| `OIDC_CLIENT_ID` | `subcontrol` | OIDC client ID |
| `AI_API_URL` | — | OpenAI-compatible API URL |
| `AI_API_KEY` | — | API key |
| `AI_MODEL` | `gpt-4o-mini` | Model name |
| `SUBCONTROL_API_URL` | `http://localhost:8000` | For MCP server |
| `SUBCONTROL_API_KEY` | — | Bearer token for MCP server |

## MCP server

```bash
# Configure in Claude Desktop (claude_desktop_config.json):
{
  "mcpServers": {
    "subcontrol": {
      "command": "python",
      "args": ["/path/to/SubControl/mcp_server/server.py"],
      "env": {
        "SUBCONTROL_API_URL": "http://localhost:8000"
      }
    }
  }
}
```

See [docs/mcp-server.md](docs/mcp-server.md) for the full tool reference.

## Documentation

| Doc | Description |
|-----|-------------|
| [docs/architecture.md](docs/architecture.md) | System architecture |
| [docs/data-model.md](docs/data-model.md) | Database schema |
| [docs/api.md](docs/api.md) | API route reference |
| [docs/auth.md](docs/auth.md) | Authentication flows |
| [docs/migrations.md](docs/migrations.md) | Database migrations |
| [docs/dashboard-logic.md](docs/dashboard-logic.md) | Monthly calculation logic |
| [docs/csv-import.md](docs/csv-import.md) | CSV import format |
| [docs/ai-chat.md](docs/ai-chat.md) | AI chat configuration |
| [docs/logo-fetch.md](docs/logo-fetch.md) | Logo fetch strategy |
| [docs/mcp-server.md](docs/mcp-server.md) | MCP server tools |
| [docs/deployment.md](docs/deployment.md) | Production deployment |

## Tech stack

- **Backend**: FastAPI, aiosqlite, pydantic-settings, python-jose, openai, mcp
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS v4, @tanstack/react-query, recharts
- **Tests**: pytest, pytest-asyncio, respx, Vitest, Playwright
- **Deployment**: Docker multi-stage build, SQLite, optional Keycloak

## License

MIT

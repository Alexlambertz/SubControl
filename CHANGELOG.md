# Changelog

All notable changes to SubControl are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
SubControl uses [Semantic Versioning](https://semver.org/).

---

## [1.0.0] — 2026-05-25

### Added

#### Backend
- FastAPI application factory with lifespan-based migration runner
- Versioned SQL migration system (`backend/migrations/runner.py`)
- Initial schema: `buckets`, `users`, `user_buckets`, `providers`, `categories`, `subscriptions`, `app_settings`, `schema_version`
- `updated_at` trigger on subscriptions table
- Dev mode: dummy admin user injected, no auth required
- Production mode: Keycloak OIDC JWT validation, first-user admin promotion
- Full CRUD routers for: buckets, users, subscriptions, providers, categories
- Dashboard service: average-monthly and real-monthly modes with per-interval factors
- Logo fetch service: Clearbit with Google Favicon fallback (async, fire-and-forget)
- CSV import service with per-row error reporting
- App settings router (admin-only) for AI configuration
- AI chat router: SSE streaming, OpenAI-compatible, tool calls for create/update subscription
- MCP server: 7 tools via stdio transport
- 95 backend tests (pytest + pytest-asyncio + respx)

#### Frontend
- React 19 + TypeScript + Vite SPA
- Tailwind CSS v4
- @tanstack/react-query for all server state
- Pages: Dashboard, Bucket List, Subscription List + Form, CSV Import, Users, Chat, Settings
- Dashboard: average/real mode toggle, month picker, bucket filter, bar chart by category
- Subscription form: modal with provider autocomplete, all interval options, logo preview
- CSV import UI with drag-and-drop and per-row result display
- AI Chat: SSE streaming chat interface with conversation history
- Settings page: AI endpoint configuration
- Global search (top bar)
- SortableTable generic component
- CurrencyDisplay, IntervalBadge, ProviderLogo components
- 13 Vitest unit tests
- Playwright E2E specs for all major flows

#### Infrastructure
- Multi-stage Dockerfile (Node build → Python serve)
- docker-compose.yml with optional Keycloak profile
- GitHub Actions CI: backend tests, frontend tests, E2E tests, Docker build smoke test

---

## [0.1.0] — 2026-05-20

### Added
- Initial project scaffold
- CLAUDE.md, README.md, .env.example
- Project specification and architecture plan

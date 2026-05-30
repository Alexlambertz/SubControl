# Deployment

## Docker (recommended)

### Quick start

```bash
cp .env.example .env
# Edit .env: set SECRET_KEY, disable DEV_MODE, configure OIDC if needed

docker compose up -d
```

The app is now available at `http://localhost:8000`.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEV_MODE` | `false` | Skip auth — ONLY for local development |
| `DATABASE_URL` | `sqlite+aiosqlite:////app/data/subcontrol.db` | SQLite path |
| `SECRET_KEY` | (required in prod) | JWT signing secret |
| `OIDC_ISSUER_URL` | — | Keycloak realm URL |
| `OIDC_CLIENT_ID` | `subcontrol` | Keycloak client ID |

### With Keycloak

```bash
docker compose --profile oidc up -d
```

Starts both SubControl and Keycloak. Access Keycloak admin at `http://localhost:8080`.

Create a realm `subcontrol`, create a public client `subcontrol` with PKCE enabled and redirect URI `http://localhost:8000/*`.

### Data persistence

SQLite is stored at `./data/subcontrol.db` (bind-mounted into the container). Back up this file to preserve all data.

## Manual / development

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e "."
DEV_MODE=true uvicorn backend.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev   # → http://localhost:5173 (proxies /api to :8000)
```

## Production checklist

- [ ] Set `DEV_MODE=false`
- [ ] Set a strong `SECRET_KEY`
- [ ] Configure Keycloak (or another OIDC provider)
- [ ] Use a reverse proxy (nginx/Caddy) with TLS in front of port 8000
- [ ] Schedule SQLite backups (`cp ./data/subcontrol.db ./backups/`)
- [ ] Set `ai_api_url` in Settings if using the AI chat feature

# ============================================================
# Stage 1: Build the React SPA
# ============================================================
FROM node:24-alpine AS frontend-builder

WORKDIR /app/frontend

# Install dependencies
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Copy source and build
COPY frontend/ .
RUN npm run build


# ============================================================
# Stage 2: Production image
# ============================================================
FROM python:3.12-slim AS production

WORKDIR /app

# System dependencies (needed for some Python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/pyproject.toml ./backend/pyproject.toml
RUN pip install --no-cache-dir -e backend/[standard] || \
    pip install --no-cache-dir \
        "fastapi>=0.111" \
        "uvicorn[standard]>=0.29" \
        "aiosqlite>=0.20" \
        "python-jose[cryptography]>=3.3" \
        "python-multipart>=0.0.9" \
        "httpx>=0.27" \
        "pydantic>=2.7" \
        "pydantic-settings>=2.3" \
        "openai>=1.30" \
        "mcp>=1.0" \
        "python-dateutil>=2.9"

# Copy backend source
COPY backend/ ./backend/
COPY VERSION ./

# Copy built frontend assets into backend/static/ for StaticFiles mounting
COPY --from=frontend-builder /app/frontend/dist/ ./backend/static/

# Data directory for SQLite persistence
RUN mkdir -p /app/data

# Default environment
ENV DATABASE_URL="sqlite+aiosqlite:////app/data/subcontrol.db"
ENV DEV_MODE="false"

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

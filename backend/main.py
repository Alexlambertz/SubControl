"""
SubControl FastAPI application factory.

The ``create_app`` factory is used both for production startup (via
``uvicorn backend.main:app``) and in tests (to get a fresh app per test).

Startup sequence
----------------
1. Run pending database migrations.
2. Register all API routers under ``/api``.
3. In production, mount the pre-built React SPA as static files at ``/``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.database import DB_PATH

# Configure application-level logging so INFO messages from backend modules
# are visible alongside uvicorn's own request logs.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[type-arg]
        """Run startup tasks before serving requests."""
        # Re-derive DB path at startup so test fixtures patching
        # settings.database_url are honoured.
        from backend.database import get_db_path
        from backend.migrations.runner import apply_pending_migrations

        db_path = get_db_path()
        logger.info("Applying database migrations to %s …", db_path)
        await apply_pending_migrations(db_path)
        logger.info("Migrations complete. SubControl is ready.")
        yield

    app = FastAPI(
        title="SubControl API",
        description="Subscription management REST API",
        version=_read_version(),
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # ------------------------------------------------------------------
    # CORS — allow the Vite dev server and the production origin
    # ------------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # API routers
    # ------------------------------------------------------------------
    _register_routers(app)

    # ------------------------------------------------------------------
    # Serve built React SPA (only when the dist directory exists)
    #
    # StaticFiles(html=True) only serves index.html for directory-like
    # paths and returns 404 for unknown routes such as /auth/callback.
    # A proper SPA catch-all is required so the React router handles all
    # client-side paths — exact static files are served as-is, everything
    # else falls back to index.html.
    # ------------------------------------------------------------------
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        # Mount /assets separately so Starlette serves them efficiently
        # with correct Content-Type headers and caching support.
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount(
                "/assets",
                StaticFiles(directory=str(assets_dir)),
                name="assets",
            )

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str) -> FileResponse:  # type: ignore[return]
            """Serve static files or fall back to the SPA index."""
            candidate = static_dir / full_path
            if candidate.is_file():
                return FileResponse(str(candidate))
            return FileResponse(str(static_dir / "index.html"))

    return app


def _register_routers(app: FastAPI) -> None:
    """Import and include all API routers."""
    from backend.routers import (
        auth, buckets, users, subscriptions, dashboard,
        import_csv, import_external, chat,
        providers_categories, search,
    )
    from backend.routers import settings as settings_router

    app.include_router(auth.router)
    app.include_router(buckets.router)
    app.include_router(users.router)
    # import_csv must be registered BEFORE subscriptions so the
    # /import path is matched before the /{sub_id} wildcard
    app.include_router(import_csv.router)
    app.include_router(subscriptions.router)
    app.include_router(dashboard.router)
    app.include_router(settings_router.router)
    app.include_router(chat.router)
    app.include_router(import_external.router)
    app.include_router(providers_categories.providers_router)
    app.include_router(providers_categories.categories_router)
    app.include_router(search.router)

    # Health check + frontend config (no auth required)
    from fastapi import APIRouter

    health_router = APIRouter(tags=["system"])

    @health_router.get("/api/health")
    async def health_check() -> dict:  # type: ignore[return]
        return {"status": "ok", "version": _read_version()}

    @health_router.get("/api/config")
    async def get_config() -> dict:  # type: ignore[return]
        """
        Return public configuration consumed by the frontend at runtime.

        This endpoint is intentionally unauthenticated so the browser can
        bootstrap the OIDC flow before any token exists.
        """
        public_issuer = (
            settings.oidc_public_issuer_url
            if settings.oidc_public_issuer_url
            else settings.oidc_issuer_url
        )
        return {
            "dev_mode": settings.dev_mode,
            "oidc_issuer_url": public_issuer,
            "oidc_client_id": settings.oidc_client_id,
            # NOTE: client_secret is intentionally NOT returned here.
            # The SPA is an OAuth 2.0 public client and uses PKCE instead.
            # A secret sent to the browser is not secret.
        }

    app.include_router(health_router)


def _read_version() -> str:
    """Read the version string from the VERSION file at the repo root."""
    version_file = Path(__file__).parent.parent / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "0.0.0"


# ---------------------------------------------------------------------------
# Module-level app instance (used by uvicorn)
# ---------------------------------------------------------------------------

app = create_app()

"""
Pytest fixtures shared across all backend tests.

Provides
--------
- ``test_db_path`` — a temporary SQLite file with migrations applied.
- ``db`` — an aiosqlite connection to the test database.
- ``client`` — an httpx.AsyncClient wired to the FastAPI app using the test DB.
- ``dev_client`` — same as ``client`` but with DEV_MODE forced on.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import AsyncGenerator

import aiosqlite
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Ensure the app always uses DEV_MODE during tests
# ---------------------------------------------------------------------------
os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key")


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture()
async def test_db_path() -> AsyncGenerator[str, None]:
    """
    Create a fresh temporary SQLite database with all migrations applied.
    Yields the filesystem path; cleans up after the test.
    """
    from backend.migrations.runner import apply_pending_migrations

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    try:
        await apply_pending_migrations(path)
        yield path
    finally:
        os.unlink(path)


@pytest_asyncio.fixture()
async def db(test_db_path: str) -> AsyncGenerator[aiosqlite.Connection, None]:
    """Open an aiosqlite connection to the test database."""
    async with aiosqlite.connect(test_db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn


@pytest_asyncio.fixture()
async def client(test_db_path: str) -> AsyncGenerator[AsyncClient, None]:
    """
    AsyncClient for the FastAPI app using the test database.
    DEV_MODE is on (via env), so auth is bypassed.
    """
    # Patch the settings singleton so that get_db() uses the test DB path.
    from backend import config as cfg
    original_url = cfg.settings.database_url
    cfg.settings.database_url = f"sqlite+aiosqlite:///{test_db_path}"

    app = None
    try:
        from backend.main import create_app

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        # ASGITransport doesn't run ASGI lifespan events, so the shared DB
        # connection get_db() lazily creates is never closed by lifespan
        # shutdown in tests — close it here instead.
        if app is not None:
            from backend.database import close_db
            await close_db(app)
        cfg.settings.database_url = original_url

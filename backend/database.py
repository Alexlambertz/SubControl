"""
Async SQLite database layer using aiosqlite.

Usage
-----
In FastAPI route handlers, inject the database connection via:

    async def my_route(db: AsyncConnection = Depends(get_db)):
        ...

The database file path is derived from config.settings.database_url.
"""

import asyncio
import aiosqlite
from pathlib import Path
from typing import AsyncGenerator

from fastapi import Request

from backend.config import settings


def _db_path() -> str:
    """Extract the filesystem path from the DATABASE_URL (SQLite-only)."""
    url = settings.database_url
    # Strip the async driver prefix: sqlite+aiosqlite:///./path → ./path
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            return url[len(prefix):]
    raise ValueError(f"Unsupported DATABASE_URL format: {url!r}")


def get_db_path() -> str:
    """Return the current database path (re-evaluated each call for test isolation)."""
    return _db_path()


# Module-level constant for use in the migration runner at startup.
# Tests override ``settings.database_url`` before calling ``create_app``.
DB_PATH: str = _db_path()


async def _create_connection() -> aiosqlite.Connection:
    db_path = _db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    return conn


async def get_db(request: Request) -> AsyncGenerator[aiosqlite.Connection, None]:
    """
    FastAPI dependency that yields a shared aiosqlite connection, cached on
    ``request.app.state`` and created lazily on first use. aiosqlite
    serializes all operations on a connection through its own background
    thread, so one shared connection is safe under concurrent requests —
    and avoids opening a brand-new connection (plus a blocking ``mkdir``)
    on every single request.

    Created lazily rather than only in the app's ``lifespan`` because the
    test suite drives the app via ``httpx.ASGITransport`` without running
    ASGI lifespan events.
    """
    state = request.app.state
    conn: aiosqlite.Connection | None = getattr(state, "db_conn", None)
    if conn is None:
        lock: asyncio.Lock | None = getattr(state, "db_conn_lock", None)
        if lock is None:
            lock = asyncio.Lock()
            state.db_conn_lock = lock
        async with lock:
            conn = getattr(state, "db_conn", None)
            if conn is None:
                conn = await _create_connection()
                state.db_conn = conn
    yield conn


async def close_db(app) -> None:
    """Close the shared connection, if one was created. Called from lifespan shutdown."""
    conn: aiosqlite.Connection | None = getattr(app.state, "db_conn", None)
    if conn is not None:
        await conn.close()
        app.state.db_conn = None

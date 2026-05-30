"""
Async SQLite database layer using aiosqlite.

Usage
-----
In FastAPI route handlers, inject the database connection via:

    async def my_route(db: AsyncConnection = Depends(get_db)):
        ...

The database file path is derived from config.settings.database_url.
"""

import aiosqlite
from pathlib import Path
from typing import AsyncGenerator

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


async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """
    FastAPI dependency that yields an open aiosqlite connection.
    The connection has row_factory set so rows behave like dicts.
    Foreign-key enforcement is enabled per connection.

    The path is re-derived from ``settings.database_url`` on every call so
    that test fixtures overriding the URL are honoured correctly.
    """
    db_path = _db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn

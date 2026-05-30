"""
Database migration runner.

Convention
----------
Migration files live in the same directory as this module and follow the
naming pattern ``NNNN_<description>.sql`` where NNNN is a zero-padded
four-digit integer (e.g. 0001_initial_schema.sql).

On every application startup ``apply_pending_migrations`` is called with the
path to the SQLite database file.  It:

1. Bootstraps the ``schema_version`` table if it doesn't exist yet.
2. Reads the highest applied version number (0 if none).
3. Scans the migrations directory for files whose prefix number exceeds the
   current version and applies them in ascending order — each inside its own
   transaction.
4. Raises ``RuntimeError`` and aborts startup if any migration fails.
"""

import logging
import re
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent

# Regex that matches the numeric prefix of a migration filename.
_VERSION_RE = re.compile(r"^(\d{4})_.+\.sql$")

_BOOTSTRAP_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _collect_migrations(above_version: int) -> list[tuple[int, Path]]:
    """Return a sorted list of (version, path) tuples for pending migrations."""
    pending: list[tuple[int, Path]] = []
    for f in MIGRATIONS_DIR.iterdir():
        m = _VERSION_RE.match(f.name)
        if m:
            v = int(m.group(1))
            if v > above_version:
                pending.append((v, f))
    pending.sort(key=lambda t: t[0])
    return pending


async def apply_pending_migrations(db_path: str) -> None:
    """
    Open *db_path* and apply all migrations whose version number is higher
    than the current ``schema_version`` max.  Called once at app startup.

    Parameters
    ----------
    db_path:
        Filesystem path to the SQLite database file.
    """
    from pathlib import Path as _Path
    _Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("PRAGMA foreign_keys = ON")

        # Ensure the version-tracking table exists (idempotent).
        await conn.execute(_BOOTSTRAP_DDL)
        await conn.commit()

        # Determine current schema version.
        async with conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()
            current_version: int = row[0] if row[0] is not None else 0

        logger.info("Current schema version: %d", current_version)

        pending = _collect_migrations(current_version)
        if not pending:
            logger.info("Database schema is up to date.")
            return

        for version, path in pending:
            sql = path.read_text(encoding="utf-8")
            logger.info("Applying migration %04d: %s", version, path.name)
            try:
                await conn.executescript(sql)
                # executescript auto-commits; record the applied version
                # outside the script so we can track it atomically.
                await conn.execute(
                    "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
                    (version,),
                )
                await conn.commit()
                logger.info("Migration %04d applied successfully.", version)
            except Exception as exc:
                logger.error("Migration %04d FAILED: %s", version, exc)
                raise RuntimeError(
                    f"Migration {version:04d} ({path.name}) failed: {exc}"
                ) from exc

        logger.info(
            "All migrations applied. Schema is now at version %d.",
            pending[-1][0],
        )

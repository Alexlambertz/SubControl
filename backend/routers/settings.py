"""
App settings router — CRUD for configurable runtime settings.

Settings are stored in the ``app_settings`` table as key/value pairs.
Default entries (ai_api_url, ai_api_key, ai_model) are seeded by migration 0002.

Routes
------
GET  /api/settings           List all settings (admin only)
GET  /api/settings/{key}     Get a single setting (admin only)
PUT  /api/settings/{key}     Upsert a setting value (admin only)
"""

from __future__ import annotations

import logging

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.database import get_db
from backend.dependencies import CurrentUser, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SettingUpdate(BaseModel):
    value: str


class SettingResponse(BaseModel):
    key: str
    value: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[SettingResponse])
async def list_settings(
    _admin: CurrentUser = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[SettingResponse]:
    """Return all app settings."""
    async with db.execute("SELECT key, value FROM app_settings ORDER BY key") as cur:
        rows = await cur.fetchall()
    return [SettingResponse(key=r["key"], value=r["value"]) for r in rows]


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(
    key: str,
    _admin: CurrentUser = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> SettingResponse:
    """Get a single setting by key."""
    async with db.execute(
        "SELECT key, value FROM app_settings WHERE key = ?", (key,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    return SettingResponse(key=row["key"], value=row["value"])


@router.put("/{key}", response_model=SettingResponse)
async def upsert_setting(
    key: str,
    body: SettingUpdate,
    _admin: CurrentUser = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> SettingResponse:
    """Create or update a setting."""
    await db.execute(
        """
        INSERT INTO app_settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                       updated_at = datetime('now')
        """,
        (key, body.value),
    )
    await db.commit()
    return SettingResponse(key=key, value=body.value)

"""
Users router — read and delete operations for user accounts.

User records are created/updated on login via /api/auth/login.
Listing and deletion require admin privileges.

Routes
------
GET    /api/users           List all users (admin only)
GET    /api/users/{id}      Get single user (admin only)
DELETE /api/users/{id}      Delete user (admin only)
"""

from __future__ import annotations

import logging

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.database import get_db
from backend.dependencies import CurrentUser, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    id: str
    username: str
    is_admin: bool
    last_login: str | None = None
    created_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_user_or_404(user_id: str, db: aiosqlite.Connection) -> dict:
    async with db.execute(
        "SELECT id, username, is_admin, last_login, created_at FROM users WHERE id = ?",
        (user_id,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {**dict(row), "is_admin": bool(row["is_admin"])}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[UserResponse])
async def list_users(
    _admin: CurrentUser = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[UserResponse]:
    """List all registered users.  Admin only."""
    async with db.execute(
        "SELECT id, username, is_admin, last_login, created_at FROM users ORDER BY username"
    ) as cur:
        rows = await cur.fetchall()
    return [UserResponse(**{**dict(r), "is_admin": bool(r["is_admin"])}) for r in rows]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    _admin: CurrentUser = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> UserResponse:
    """Get a single user by ID.  Admin only."""
    return UserResponse(**await _get_user_or_404(user_id, db))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    _admin: CurrentUser = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> None:
    """Delete a user and their bucket memberships (cascade).  Admin only."""
    await _get_user_or_404(user_id, db)
    await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    await db.commit()
    logger.info("User %r deleted.", user_id)

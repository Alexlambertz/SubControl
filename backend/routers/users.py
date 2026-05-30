"""
Users router — read, update, and delete operations for user accounts.

User records are created/updated on login via /api/auth/login.
Listing and deletion require admin privileges.

Routes
------
GET    /api/users                   List all users (admin only)
GET    /api/users/{id}              Get single user (admin only)
PATCH  /api/users/{id}              Update user (admin only) — currently: is_admin toggle
GET    /api/users/{id}/buckets      List bucket IDs the user is assigned to (admin only)
DELETE /api/users/{id}              Delete user (admin only)
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


class UserUpdate(BaseModel):
    is_admin: bool


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


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: UserUpdate,
    admin: CurrentUser = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> UserResponse:
    """Update a user's properties (currently: is_admin).  Admin only."""
    if user_id == admin.id and not body.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove your own admin privileges",
        )
    await _get_user_or_404(user_id, db)
    await db.execute(
        "UPDATE users SET is_admin = ? WHERE id = ?",
        (int(body.is_admin), user_id),
    )
    await db.commit()
    logger.info("User %r is_admin set to %s by %r.", user_id, body.is_admin, admin.username)
    return UserResponse(**await _get_user_or_404(user_id, db))


@router.get("/{user_id}/buckets", response_model=list[str])
async def get_user_buckets(
    user_id: str,
    _admin: CurrentUser = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[str]:
    """Return the IDs of all buckets the user is assigned to.  Admin only."""
    await _get_user_or_404(user_id, db)
    async with db.execute(
        "SELECT bucket_id FROM user_buckets WHERE user_id = ?", (user_id,)
    ) as cur:
        rows = await cur.fetchall()
    return [row["bucket_id"] for row in rows]


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

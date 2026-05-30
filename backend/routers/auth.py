"""
Authentication router.

Routes
------
GET  /api/auth/me   → Return the current user's profile.
POST /api/auth/login → Upsert user from OIDC token, set last_login,
                       promote first user to admin.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import aiosqlite
from backend.database import get_db
from backend.dependencies import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class UserProfile(BaseModel):
    id: str
    username: str
    is_admin: bool
    last_login: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/me", response_model=UserProfile)
async def get_me(
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> UserProfile:
    """Return the profile of the currently authenticated user."""
    # Look up the user in the database for last_login etc.
    async with db.execute(
        "SELECT id, username, is_admin, last_login FROM users WHERE id = ?",
        (user.id,),
    ) as cursor:
        row = await cursor.fetchone()

    if row:
        return UserProfile(
            id=row["id"],
            username=row["username"],
            is_admin=bool(row["is_admin"]),
            last_login=row["last_login"],
        )

    # User not yet in DB (first request in dev mode) — return from token
    return UserProfile(
        id=user.id,
        username=user.username,
        is_admin=user.is_admin,
    )


@router.post("/login", response_model=UserProfile)
async def login(
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> UserProfile:
    """
    Upsert the authenticated user into the database.

    - Sets ``last_login`` to now.
    - The **first** user to log in is automatically promoted to admin.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Check if any users exist yet (determines admin promotion)
    async with db.execute("SELECT COUNT(*) FROM users") as cur:
        count_row = await cur.fetchone()
        is_first_user = (count_row[0] == 0)

    is_admin = user.is_admin or is_first_user

    await db.execute(
        """
        INSERT INTO users (id, username, is_admin, last_login)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            username   = excluded.username,
            is_admin   = CASE WHEN is_admin = 1 THEN 1 ELSE excluded.is_admin END,
            last_login = excluded.last_login
        """,
        (user.id, user.username, int(is_admin), now),
    )
    await db.commit()

    logger.info(
        "User %r logged in (admin=%s, first_user=%s)", user.username, is_admin, is_first_user
    )

    return UserProfile(
        id=user.id,
        username=user.username,
        is_admin=is_admin,
        last_login=now,
    )

"""
Authentication router.

Routes
------
GET  /api/auth/me       → Return the current user's profile.
POST /api/auth/login    → Upsert user from OIDC token, set last_login,
                          promote first user to admin.
POST /api/auth/exchange → Exchange an OIDC authorization code for an
                          access token. The client_secret (for confidential
                          Keycloak clients) is added server-side so it is
                          never exposed to the browser.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

import aiosqlite
from backend.config import settings
from backend.database import get_db
from backend.dependencies import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class UserProfile(BaseModel):
    id: str
    username: str
    is_admin: bool
    last_login: str | None = None


class CodeExchangeRequest(BaseModel):
    code: str
    code_verifier: str
    redirect_uri: str


class RefreshRequest(BaseModel):
    refresh_token: str


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


@router.post("/exchange")
async def exchange_code(body: CodeExchangeRequest) -> dict:
    """
    Exchange an OIDC authorization code for an access token.

    This endpoint exists so the browser never needs the client_secret:
    the frontend sends the authorization code + PKCE code_verifier here,
    and the backend appends the client_secret before forwarding to Keycloak.

    Works for both public clients (no secret) and confidential clients.
    """
    token_url = (
        f"{settings.oidc_issuer_url}/protocol/openid-connect/token"
    )

    form: dict[str, str] = {
        "grant_type": "authorization_code",
        "client_id": settings.oidc_client_id,
        "code": body.code,
        "code_verifier": body.code_verifier,
        "redirect_uri": body.redirect_uri,
    }

    # Add secret only when the Keycloak client is confidential
    if settings.oidc_client_secret:
        form["client_secret"] = settings.oidc_client_secret

    logger.info(
        "Token exchange → %s  client_id=%r  has_secret=%s  redirect_uri=%r",
        token_url,
        settings.oidc_client_id,
        bool(settings.oidc_client_secret),
        body.redirect_uri,
    )

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(token_url, data=form, timeout=10)

        if resp.status_code != 200:
            logger.warning(
                "Token exchange failed (%s): %s", resp.status_code, resp.text
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token exchange failed",
            )

        token_data = resp.json()
        return {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "expires_in": token_data.get("expires_in", 300),
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Token exchange error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach authentication server",
        ) from exc


@router.post("/refresh")
async def refresh_token(body: RefreshRequest) -> dict:
    """
    Exchange a refresh token for a new access token.

    Called by the frontend when the access token is about to expire or
    has expired. The client_secret is added server-side when required.
    """
    token_url = f"{settings.oidc_issuer_url}/protocol/openid-connect/token"

    form: dict[str, str] = {
        "grant_type": "refresh_token",
        "client_id": settings.oidc_client_id,
        "refresh_token": body.refresh_token,
    }
    if settings.oidc_client_secret:
        form["client_secret"] = settings.oidc_client_secret

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(token_url, data=form, timeout=10)

        if resp.status_code != 200:
            logger.warning("Token refresh failed (%s): %s", resp.status_code, resp.text)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token refresh failed",
            )

        token_data = resp.json()
        return {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "expires_in": token_data.get("expires_in", 300),
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Token refresh error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach authentication server",
        ) from exc

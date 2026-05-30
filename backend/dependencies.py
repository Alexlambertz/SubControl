"""
FastAPI dependency providers.

get_current_user
----------------
In development mode (DEV_MODE=true) a fixed dummy admin user is returned
without any token validation.  This allows local testing without Keycloak.

In production mode the Authorization header is validated as a Bearer JWT
issued by the configured Keycloak realm.  The JWKS endpoint is fetched once
and cached for the lifetime of the process.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# User dataclass (lightweight; not stored in DB directly by this module)
# ---------------------------------------------------------------------------


@dataclass
class CurrentUser:
    """Represents the authenticated user for the current request."""

    id: str
    username: str
    is_admin: bool


# Dummy user injected in DEV_MODE
_DEV_USER = CurrentUser(
    id="00000000000000000000000000000001",
    username="dev_admin",
    is_admin=True,
)

# ---------------------------------------------------------------------------
# HTTP Bearer scheme (optional so dev mode can omit the header entirely)
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> CurrentUser:
    """
    Return the current authenticated user.

    - DEV_MODE=true  → always returns the dummy admin user.
    - DEV_MODE=false → validates the Bearer JWT from Keycloak.
    """
    if settings.dev_mode:
        return _DEV_USER

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    return await _validate_jwt(token)


async def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Dependency that requires the current user to be an admin."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user


# ---------------------------------------------------------------------------
# JWT validation (production path)
# ---------------------------------------------------------------------------

_jwks_cache: Optional[dict] = None


async def _validate_jwt(token: str) -> CurrentUser:
    """
    Validate a Keycloak-issued JWT.

    Fetches the JWKS from the Keycloak issuer on first call and caches it
    for subsequent requests.  Raises HTTP 401 on any validation failure.
    """
    import httpx
    from jose import JWTError, jwt

    global _jwks_cache

    try:
        # Fetch JWKS if not cached
        if _jwks_cache is None:
            jwks_url = f"{settings.oidc_issuer_url}/protocol/openid-connect/certs"
            async with httpx.AsyncClient() as client:
                resp = await client.get(jwks_url, timeout=5)
                resp.raise_for_status()
                _jwks_cache = resp.json()

        # Decode and validate
        payload = jwt.decode(
            token,
            _jwks_cache,
            algorithms=["RS256"],
            audience=settings.oidc_client_id,
            issuer=settings.oidc_issuer_url,
        )

        return CurrentUser(
            id=payload.get("sub", ""),
            username=payload.get("preferred_username", payload.get("sub", "")),
            is_admin="admin" in payload.get("realm_access", {}).get("roles", []),
        )

    except JWTError as exc:
        logger.warning("JWT validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except Exception as exc:
        logger.error("Unexpected auth error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        ) from exc

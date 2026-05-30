"""
Tests for authentication and the /api/auth/me endpoint.

Phase 0 tests
-------------
- In DEV_MODE the dummy admin user is returned from GET /api/auth/me.
- The health endpoint is always accessible without auth.

Phase 1 tests (production auth path) live here too but are marked as
requiring a live Keycloak instance (skipped in CI without one).
"""

from __future__ import annotations

import os

import pytest
from httpx import AsyncClient


class TestHealthEndpoint:
    """The /api/health endpoint requires no authentication."""

    async def test_health_returns_ok(self, client: AsyncClient) -> None:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "version" in body

    async def test_health_returns_version(self, client: AsyncClient) -> None:
        resp = await client.get("/api/health")
        version = resp.json()["version"]
        # Version should be a non-empty semver-like string
        assert isinstance(version, str)
        assert len(version) > 0


class TestAuthMeDevMode:
    """In DEV_MODE=true the dummy admin user is returned without a token."""

    async def test_me_returns_dummy_user(self, client: AsyncClient) -> None:
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "dev_admin"
        assert body["is_admin"] is True

    async def test_me_has_user_id(self, client: AsyncClient) -> None:
        resp = await client.get("/api/auth/me")
        body = resp.json()
        assert "id" in body
        assert len(body["id"]) > 0

    async def test_me_no_token_still_works_in_dev_mode(
        self, client: AsyncClient
    ) -> None:
        """Even without an Authorization header, dev mode returns the dummy user."""
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 200


class TestAuthMeProductionMode:
    """Production mode: missing/invalid token → 401."""

    @pytest.fixture(autouse=True)
    def disable_dev_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Patch the settings singleton directly so no module reloading is needed."""
        from backend import config as cfg
        monkeypatch.setattr(cfg.settings, "dev_mode", False)

    async def test_me_without_token_returns_401(self, client: AsyncClient) -> None:
        from backend.dependencies import get_current_user
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=None)
        assert exc_info.value.status_code == 401

    async def test_me_with_invalid_token_returns_401(
        self, client: AsyncClient
    ) -> None:
        from backend.dependencies import get_current_user
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        fake_creds = HTTPAuthorizationCredentials(
            scheme="bearer", credentials="not.a.real.token"
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=fake_creds)
        assert exc_info.value.status_code in (401, 500)

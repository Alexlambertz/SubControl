"""
Tests for /api/settings (app settings CRUD).
"""

from __future__ import annotations

from httpx import AsyncClient


class TestSettings:
    async def test_get_settings_returns_list(self, client: AsyncClient) -> None:
        resp = await client.get("/api/settings")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_default_settings_seeded(self, client: AsyncClient) -> None:
        resp = await client.get("/api/settings")
        keys = [s["key"] for s in resp.json()]
        assert "ai_api_url" in keys
        assert "ai_api_key" in keys
        assert "ai_model" in keys

    async def test_update_setting(self, client: AsyncClient) -> None:
        resp = await client.put(
            "/api/settings/ai_model",
            json={"value": "gpt-4o"},
        )
        assert resp.status_code == 200
        assert resp.json()["value"] == "gpt-4o"

    async def test_update_creates_new_key(self, client: AsyncClient) -> None:
        resp = await client.put(
            "/api/settings/custom_key",
            json={"value": "custom_value"},
        )
        assert resp.status_code == 200
        assert resp.json()["key"] == "custom_key"

    async def test_get_single_setting(self, client: AsyncClient) -> None:
        await client.put("/api/settings/ai_model", json={"value": "gpt-4o-mini"})
        resp = await client.get("/api/settings/ai_model")
        assert resp.status_code == 200
        assert resp.json()["value"] == "gpt-4o-mini"

    async def test_get_nonexistent_setting_returns_404(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get("/api/settings/does_not_exist")
        assert resp.status_code == 404

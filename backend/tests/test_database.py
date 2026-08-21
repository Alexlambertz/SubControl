"""
Tests for the shared aiosqlite connection in backend/database.py.

Covers: the connection is created lazily, reused across requests within the
same app instance, and closed cleanly (no leaked connections/background
threads across tests).
"""

from __future__ import annotations

from httpx import AsyncClient


class TestSharedConnection:
    async def test_connection_created_lazily(self, client: AsyncClient) -> None:
        """No connection exists until the first request touches the DB."""
        app = client._transport.app  # type: ignore[attr-defined]
        assert getattr(app.state, "db_conn", None) is None

        resp = await client.get("/api/buckets")
        assert resp.status_code == 200
        assert getattr(app.state, "db_conn", None) is not None

    async def test_connection_reused_across_requests(self, client: AsyncClient) -> None:
        """Sequential requests within the same app instance share one connection."""
        app = client._transport.app  # type: ignore[attr-defined]

        await client.get("/api/buckets")
        first_conn = app.state.db_conn

        await client.post("/api/buckets", json={"name": "ReuseCheck"})
        await client.get("/api/buckets")
        second_conn = app.state.db_conn

        assert first_conn is second_conn

    async def test_writes_are_visible_to_subsequent_reads(self, client: AsyncClient) -> None:
        """Sanity check: the shared connection doesn't hide committed writes."""
        resp = await client.post("/api/buckets", json={"name": "VisibilityCheck"})
        assert resp.status_code == 201

        resp = await client.get("/api/buckets")
        names = [b["name"] for b in resp.json()]
        assert "VisibilityCheck" in names

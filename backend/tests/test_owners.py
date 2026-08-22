"""
Tests for /api/buckets/{bucket_id}/owners.

Covers: CRUD, bucket-scoping (unlike providers/categories, owners are
per-bucket, not global), duplicate-name 409, and cascade delete when the
owning bucket is removed.
"""

from __future__ import annotations

import aiosqlite
import pytest
from httpx import AsyncClient


async def _create_bucket(client: AsyncClient, name: str = "TestBucket") -> str:
    resp = await client.post("/api/buckets", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


class TestListCreateOwners:
    async def test_empty_list(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "EmptyOwners")
        resp = await client.get(f"/api/buckets/{bid}/owners")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_owner(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "CreateOwner")
        resp = await client.post(f"/api/buckets/{bid}/owners", json={"name": "Alex"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Alex"
        assert isinstance(body["id"], int)

    async def test_list_returns_sorted_by_name(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "SortedOwners")
        await client.post(f"/api/buckets/{bid}/owners", json={"name": "Zoe"})
        await client.post(f"/api/buckets/{bid}/owners", json={"name": "Alex"})
        resp = await client.get(f"/api/buckets/{bid}/owners")
        names = [o["name"] for o in resp.json()]
        assert names == ["Alex", "Zoe"]

    async def test_duplicate_name_in_same_bucket_returns_409(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client, "DupOwner")
        first = await client.post(f"/api/buckets/{bid}/owners", json={"name": "Alex"})
        assert first.status_code == 201
        second = await client.post(f"/api/buckets/{bid}/owners", json={"name": "Alex"})
        assert second.status_code == 409

    async def test_same_name_allowed_in_different_buckets(
        self, client: AsyncClient
    ) -> None:
        """Unlike global providers/categories, owners are scoped per bucket."""
        bid1 = await _create_bucket(client, "BucketOne")
        bid2 = await _create_bucket(client, "BucketTwo")
        resp1 = await client.post(f"/api/buckets/{bid1}/owners", json={"name": "Alex"})
        resp2 = await client.post(f"/api/buckets/{bid2}/owners", json={"name": "Alex"})
        assert resp1.status_code == 201
        assert resp2.status_code == 201

    async def test_owner_from_one_bucket_not_visible_in_another(
        self, client: AsyncClient
    ) -> None:
        bid1 = await _create_bucket(client, "OwnerScopeA")
        bid2 = await _create_bucket(client, "OwnerScopeB")
        await client.post(f"/api/buckets/{bid1}/owners", json={"name": "Alex"})

        resp = await client.get(f"/api/buckets/{bid2}/owners")
        assert resp.json() == []

    async def test_empty_name_rejected(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "EmptyNameOwner")
        resp = await client.post(f"/api/buckets/{bid}/owners", json={"name": "   "})
        assert resp.status_code == 422

    async def test_create_owner_on_missing_bucket_returns_404(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post("/api/buckets/no-such-bucket/owners", json={"name": "Alex"})
        assert resp.status_code == 404


class TestOwnerCascadeDelete:
    async def test_deleting_bucket_removes_its_owners(
        self, client: AsyncClient, db: aiosqlite.Connection
    ) -> None:
        bid = await _create_bucket(client, "CascadeOwnerBucket")
        create_resp = await client.post(f"/api/buckets/{bid}/owners", json={"name": "Alex"})
        owner_id = create_resp.json()["id"]

        del_resp = await client.delete(f"/api/buckets/{bid}")
        assert del_resp.status_code == 204

        async with db.execute(
            "SELECT COUNT(*) AS n FROM owners WHERE id = ?", (owner_id,)
        ) as cur:
            row = await cur.fetchone()
        assert row["n"] == 0

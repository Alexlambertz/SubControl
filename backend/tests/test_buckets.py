"""
Tests for the /api/buckets endpoints.

Covers: list, create, get, update, delete, user assignment.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestListBuckets:
    async def test_empty_list(self, client: AsyncClient) -> None:
        resp = await client.get("/api/buckets")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_created_bucket(self, client: AsyncClient) -> None:
        await client.post("/api/buckets", json={"name": "Home"})
        resp = await client.get("/api/buckets")
        assert resp.status_code == 200
        names = [b["name"] for b in resp.json()]
        assert "Home" in names


class TestCreateBucket:
    async def test_create_returns_201(self, client: AsyncClient) -> None:
        resp = await client.post("/api/buckets", json={"name": "Work"})
        assert resp.status_code == 201

    async def test_create_returns_bucket_with_id(self, client: AsyncClient) -> None:
        resp = await client.post("/api/buckets", json={"name": "Travel"})
        body = resp.json()
        assert "id" in body
        assert body["name"] == "Travel"

    async def test_create_duplicate_name_returns_409(self, client: AsyncClient) -> None:
        await client.post("/api/buckets", json={"name": "Unique"})
        resp = await client.post("/api/buckets", json={"name": "Unique"})
        assert resp.status_code == 409

    async def test_create_empty_name_returns_422(self, client: AsyncClient) -> None:
        resp = await client.post("/api/buckets", json={"name": ""})
        assert resp.status_code == 422


class TestGetBucket:
    async def test_get_existing_bucket(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/buckets", json={"name": "Fetch Me"})
        bucket_id = create_resp.json()["id"]
        resp = await client.get(f"/api/buckets/{bucket_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Fetch Me"

    async def test_get_nonexistent_returns_404(self, client: AsyncClient) -> None:
        resp = await client.get("/api/buckets/nonexistent-id")
        assert resp.status_code == 404


class TestUpdateBucket:
    async def test_rename_bucket(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/buckets", json={"name": "Old Name"})
        bucket_id = create_resp.json()["id"]
        resp = await client.put(f"/api/buckets/{bucket_id}", json={"name": "New Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    async def test_update_nonexistent_returns_404(self, client: AsyncClient) -> None:
        resp = await client.put("/api/buckets/bad-id", json={"name": "X"})
        assert resp.status_code == 404

    async def test_id_is_not_changed(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/buckets", json={"name": "Keep ID"})
        original_id = create_resp.json()["id"]
        await client.put(f"/api/buckets/{original_id}", json={"name": "Renamed"})
        get_resp = await client.get(f"/api/buckets/{original_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == original_id


class TestDeleteBucket:
    async def test_delete_existing_bucket(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/buckets", json={"name": "ToDelete"})
        bucket_id = create_resp.json()["id"]
        del_resp = await client.delete(f"/api/buckets/{bucket_id}")
        assert del_resp.status_code == 204
        get_resp = await client.get(f"/api/buckets/{bucket_id}")
        assert get_resp.status_code == 404

    async def test_delete_nonexistent_returns_404(self, client: AsyncClient) -> None:
        resp = await client.delete("/api/buckets/no-such-id")
        assert resp.status_code == 404

"""
Tests for /api/users and user-bucket assignment.

Covers: list users (admin only), first-login admin promotion,
        bucket assignment, user deletion.
"""

from __future__ import annotations

from httpx import AsyncClient


class TestLoginAdminPromotion:
    async def test_first_login_becomes_admin(self, client: AsyncClient) -> None:
        """The first user to POST /api/auth/login should be promoted to admin."""
        resp = await client.post("/api/auth/login")
        assert resp.status_code == 200
        body = resp.json()
        # dev_admin user is always first in a fresh DB
        assert body["is_admin"] is True

    async def test_login_sets_last_login(self, client: AsyncClient) -> None:
        resp = await client.post("/api/auth/login")
        body = resp.json()
        assert body["last_login"] is not None


class TestListUsers:
    async def test_list_users_returns_200(self, client: AsyncClient) -> None:
        # First ensure the dummy user is in the DB
        await client.post("/api/auth/login")
        resp = await client.get("/api/users")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_list_users_contains_logged_in_user(
        self, client: AsyncClient
    ) -> None:
        await client.post("/api/auth/login")
        resp = await client.get("/api/users")
        usernames = [u["username"] for u in resp.json()]
        assert "dev_admin" in usernames


class TestGetUser:
    async def test_get_user_by_id(self, client: AsyncClient) -> None:
        login_resp = await client.post("/api/auth/login")
        user_id = login_resp.json()["id"]
        resp = await client.get(f"/api/users/{user_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == user_id

    async def test_get_nonexistent_user_returns_404(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get("/api/users/no-such-id")
        assert resp.status_code == 404


class TestUserBucketAssignment:
    async def test_assign_user_to_bucket(self, client: AsyncClient) -> None:
        login_resp = await client.post("/api/auth/login")
        user_id = login_resp.json()["id"]
        bucket_resp = await client.post("/api/buckets", json={"name": "Assigned"})
        bucket_id = bucket_resp.json()["id"]

        resp = await client.post(f"/api/buckets/{bucket_id}/users/{user_id}")
        assert resp.status_code == 200

    async def test_remove_user_from_bucket(self, client: AsyncClient) -> None:
        login_resp = await client.post("/api/auth/login")
        user_id = login_resp.json()["id"]
        bucket_resp = await client.post("/api/buckets", json={"name": "ToUnassign"})
        bucket_id = bucket_resp.json()["id"]

        await client.post(f"/api/buckets/{bucket_id}/users/{user_id}")
        resp = await client.delete(f"/api/buckets/{bucket_id}/users/{user_id}")
        assert resp.status_code == 200

    async def test_assign_nonexistent_user_returns_404(
        self, client: AsyncClient
    ) -> None:
        bucket_resp = await client.post("/api/buckets", json={"name": "NoBucket"})
        bucket_id = bucket_resp.json()["id"]
        resp = await client.post(f"/api/buckets/{bucket_id}/users/ghost-user-id")
        assert resp.status_code == 404

    async def test_assign_to_nonexistent_bucket_returns_404(
        self, client: AsyncClient
    ) -> None:
        login_resp = await client.post("/api/auth/login")
        user_id = login_resp.json()["id"]
        resp = await client.post(f"/api/buckets/no-bucket/users/{user_id}")
        assert resp.status_code == 404


class TestDeleteUser:
    async def test_delete_user(self, client: AsyncClient) -> None:
        login_resp = await client.post("/api/auth/login")
        user_id = login_resp.json()["id"]
        resp = await client.delete(f"/api/users/{user_id}")
        assert resp.status_code == 204

    async def test_delete_nonexistent_user_returns_404(
        self, client: AsyncClient
    ) -> None:
        resp = await client.delete("/api/users/nobody")
        assert resp.status_code == 404

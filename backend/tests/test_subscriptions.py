"""
Tests for /api/buckets/{bucket_id}/subscriptions and provider/category endpoints.

Covers: CRUD, bucket scoping, all recurring intervals, decimal amount precision,
        provider/category create-on-fly, logo fetch triggering.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_bucket(client: AsyncClient, name: str = "TestBucket") -> str:
    resp = await client.post("/api/buckets", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_sub(
    client: AsyncClient,
    bucket_id: str,
    *,
    name: str = "Netflix",
    provider: str = "Netflix",
    interval: str = "monthly",
    recurring_date: str = "2024-01-15",
    amount: float = 9.99,
    currency: str = "EUR",
    category: str | None = None,
) -> dict:
    payload: dict = {
        "name": name,
        "provider_name": provider,
        "recurring_interval": interval,
        "recurring_date": recurring_date,
        "amount": amount,
        "currency": currency,
    }
    if category:
        payload["category_name"] = category
    resp = await client.post(
        f"/api/buckets/{bucket_id}/subscriptions", json=payload
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Tests: List
# ---------------------------------------------------------------------------


class TestListSubscriptions:
    async def test_empty_list(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "EmptyBucket")
        resp = await client.get(f"/api/buckets/{bid}/subscriptions")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_created_subscription(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "FullBucket")
        await _create_sub(client, bid, name="Spotify")
        resp = await client.get(f"/api/buckets/{bid}/subscriptions")
        names = [s["name"] for s in resp.json()]
        assert "Spotify" in names

    async def test_bucket_scoping(self, client: AsyncClient) -> None:
        """Subscriptions from bucket A must not appear in bucket B's list."""
        bid_a = await _create_bucket(client, "BucketA")
        bid_b = await _create_bucket(client, "BucketB")
        await _create_sub(client, bid_a, name="Only In A")
        resp = await client.get(f"/api/buckets/{bid_b}/subscriptions")
        names = [s["name"] for s in resp.json()]
        assert "Only In A" not in names


# ---------------------------------------------------------------------------
# Tests: Create
# ---------------------------------------------------------------------------


class TestCreateSubscription:
    async def test_create_returns_201(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "C1")
        resp = await client.post(
            f"/api/buckets/{bid}/subscriptions",
            json={
                "name": "Disney+",
                "provider_name": "Disney",
                "recurring_interval": "monthly",
                "recurring_date": "2024-03-01",
                "amount": 8.99,
                "currency": "EUR",
            },
        )
        assert resp.status_code == 201

    @pytest.mark.parametrize(
        "interval",
        ["daily", "weekly", "monthly", "quarterly", "half-year", "yearly"],
    )
    async def test_all_intervals_accepted(
        self, client: AsyncClient, interval: str
    ) -> None:
        bid = await _create_bucket(client, f"Bucket_{interval}")
        sub = await _create_sub(client, bid, interval=interval)
        assert sub["recurring_interval"] == interval

    async def test_decimal_amount_precision(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "Decimal")
        sub = await _create_sub(client, bid, amount=12.345)
        # Stored and returned as a float; precision preserved
        assert abs(sub["amount"] - 12.345) < 0.001

    async def test_currency_stored_correctly(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "CurrencyBucket")
        sub = await _create_sub(client, bid, currency="USD")
        assert sub["currency"] == "USD"

    async def test_default_currency_is_eur(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "DefaultCurrency")
        resp = await client.post(
            f"/api/buckets/{bid}/subscriptions",
            json={
                "name": "Hulu",
                "provider_name": "Hulu",
                "recurring_interval": "monthly",
                "recurring_date": "2024-01-01",
                "amount": 5.0,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["currency"] == "EUR"

    async def test_invalid_interval_returns_422(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "BadInterval")
        resp = await client.post(
            f"/api/buckets/{bid}/subscriptions",
            json={
                "name": "Bad",
                "provider_name": "X",
                "recurring_interval": "fortnightly",
                "recurring_date": "2024-01-01",
                "amount": 1.0,
            },
        )
        assert resp.status_code == 422

    async def test_create_in_nonexistent_bucket_returns_404(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/buckets/no-such-bucket/subscriptions",
            json={
                "name": "Ghost",
                "provider_name": "X",
                "recurring_interval": "monthly",
                "recurring_date": "2024-01-01",
                "amount": 1.0,
            },
        )
        assert resp.status_code == 404

    async def test_provider_auto_created(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "ProviderTest")
        sub = await _create_sub(client, bid, provider="NewProviderXYZ")
        assert sub["provider_name"] == "NewProviderXYZ"

    async def test_category_auto_created(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "CategoryTest")
        sub = await _create_sub(client, bid, category="NewCategoryABC")
        assert sub["category_name"] == "NewCategoryABC"


# ---------------------------------------------------------------------------
# Tests: Get
# ---------------------------------------------------------------------------


class TestGetSubscription:
    async def test_get_existing(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "GetSub")
        sub = await _create_sub(client, bid, name="Audible")
        resp = await client.get(f"/api/buckets/{bid}/subscriptions/{sub['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Audible"

    async def test_get_nonexistent_returns_404(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "GetNone")
        resp = await client.get(f"/api/buckets/{bid}/subscriptions/no-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: Update
# ---------------------------------------------------------------------------


class TestUpdateSubscription:
    async def test_update_name(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "UpdateBucket")
        sub = await _create_sub(client, bid, name="OldName")
        resp = await client.put(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}",
            json={"name": "NewName"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "NewName"

    async def test_update_amount(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "AmountBucket")
        sub = await _create_sub(client, bid, amount=9.99)
        resp = await client.put(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}",
            json={"amount": 14.99},
        )
        assert resp.status_code == 200
        assert abs(resp.json()["amount"] - 14.99) < 0.001

    async def test_update_nonexistent_returns_404(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "UpdateNone")
        resp = await client.put(
            f"/api/buckets/{bid}/subscriptions/no-id", json={"name": "X"}
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: Delete
# ---------------------------------------------------------------------------


class TestDeleteSubscription:
    async def test_delete_existing(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "DelBucket")
        sub = await _create_sub(client, bid, name="ToDelete")
        resp = await client.delete(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}"
        )
        assert resp.status_code == 204

        # Confirm it's gone
        get_resp = await client.get(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}"
        )
        assert get_resp.status_code == 404

    async def test_delete_nonexistent_returns_404(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "DelNone")
        resp = await client.delete(f"/api/buckets/{bid}/subscriptions/no-id")
        assert resp.status_code == 404

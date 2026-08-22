"""
Tests for /api/buckets/{bucket_id}/subscriptions and provider/category endpoints.

Covers: CRUD, bucket scoping, all recurring intervals, decimal amount precision,
        provider/category create-on-fly, logo fetch triggering.
"""

from __future__ import annotations

import aiosqlite
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

    async def test_explicit_null_clears_end_date(self, client: AsyncClient) -> None:
        """Regression: an explicit null must clear end_date, not be ignored."""
        bid = await _create_bucket(client, "ClearEndDate")
        sub = await _create_sub(client, bid)
        set_resp = await client.put(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}",
            json={"end_date": "2026-12-31"},
        )
        assert set_resp.json()["end_date"] == "2026-12-31"

        clear_resp = await client.put(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}",
            json={"end_date": None},
        )
        assert clear_resp.status_code == 200
        assert clear_resp.json()["end_date"] is None

    async def test_omitted_end_date_is_preserved(self, client: AsyncClient) -> None:
        """An update that doesn't mention end_date at all must leave it alone."""
        bid = await _create_bucket(client, "PreserveEndDate")
        sub = await _create_sub(client, bid)
        await client.put(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}",
            json={"end_date": "2026-12-31"},
        )
        resp = await client.put(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}",
            json={"amount": 42.0},
        )
        assert resp.status_code == 200
        assert resp.json()["end_date"] == "2026-12-31"
        assert resp.json()["amount"] == pytest.approx(42.0)

    async def test_explicit_null_clears_category(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "ClearCategory")
        sub = await _create_sub(client, bid, category="Streaming")
        assert sub["category_name"] == "Streaming"

        resp = await client.put(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}",
            json={"category_name": None},
        )
        assert resp.status_code == 200
        assert resp.json()["category_name"] is None


# ---------------------------------------------------------------------------
# Tests: Change history
# ---------------------------------------------------------------------------


class TestSubscriptionHistory:
    async def test_update_records_history(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "HistoryBucket")
        sub = await _create_sub(client, bid, amount=9.99)
        resp = await client.put(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}",
            json={"amount": 14.99},
        )
        assert resp.status_code == 200

        hist_resp = await client.get(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}/history"
        )
        assert hist_resp.status_code == 200
        entries = hist_resp.json()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["field"] == "amount"
        assert entry["old_value"] == "9.99"
        assert entry["new_value"] == "14.99"
        assert entry["changed_by_username"] == "dev_admin"
        assert entry["changed_at"]

    async def test_partial_update_records_only_changed_fields(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client, "PartialHistoryBucket")
        sub = await _create_sub(client, bid, amount=9.99)
        resp = await client.put(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}",
            json={"name": "RenamedOnly"},
        )
        assert resp.status_code == 200

        hist_resp = await client.get(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}/history"
        )
        entries = hist_resp.json()
        assert len(entries) == 1
        assert entries[0]["field"] == "name"

    async def test_create_does_not_record_history(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "NoHistoryOnCreate")
        sub = await _create_sub(client, bid)

        hist_resp = await client.get(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}/history"
        )
        assert hist_resp.json() == []

    async def test_unchanged_update_records_nothing(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "NoOpUpdateBucket")
        sub = await _create_sub(client, bid, amount=9.99)
        resp = await client.put(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}",
            json={"amount": 9.99},
        )
        assert resp.status_code == 200

        hist_resp = await client.get(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}/history"
        )
        assert hist_resp.json() == []

    async def test_image_url_change_excluded_from_history(
        self, client: AsyncClient
    ) -> None:
        """image_url is refreshed by a background logo job, not a user edit."""
        bid = await _create_bucket(client, "ImageUrlHistoryBucket")
        sub = await _create_sub(client, bid)
        resp = await client.put(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}",
            json={"image_url": "https://example.com/logo.png"},
        )
        assert resp.status_code == 200

        hist_resp = await client.get(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}/history"
        )
        assert hist_resp.json() == []

    async def test_history_not_found_for_missing_sub(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client, "MissingSubHistory")
        resp = await client.get(f"/api/buckets/{bid}/subscriptions/no-id/history")
        assert resp.status_code == 404

    async def test_delete_cascades_history(
        self, client: AsyncClient, db: aiosqlite.Connection
    ) -> None:
        bid = await _create_bucket(client, "CascadeHistoryBucket")
        sub = await _create_sub(client, bid, amount=9.99)
        await client.put(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}",
            json={"amount": 14.99},
        )
        del_resp = await client.delete(
            f"/api/buckets/{bid}/subscriptions/{sub['id']}"
        )
        assert del_resp.status_code == 204

        async with db.execute(
            "SELECT COUNT(*) AS n FROM subscription_history WHERE subscription_id = ?",
            (sub["id"],),
        ) as cur:
            row = await cur.fetchone()
        assert row["n"] == 0


# ---------------------------------------------------------------------------
# Tests: Bulk update
# ---------------------------------------------------------------------------


class TestBulkUpdateSubscriptions:
    async def test_bulk_update_applies_field_to_all(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "BulkBucket")
        sub1 = await _create_sub(client, bid, name="Sub1", amount=5.0)
        sub2 = await _create_sub(client, bid, name="Sub2", amount=7.0)

        resp = await client.patch(
            f"/api/buckets/{bid}/subscriptions/bulk",
            json={"ids": [sub1["id"], sub2["id"]], "update": {"amount": 19.99}},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 2

        for sub_id in (sub1["id"], sub2["id"]):
            get_resp = await client.get(f"/api/buckets/{bid}/subscriptions/{sub_id}")
            assert get_resp.json()["amount"] == pytest.approx(19.99)

    async def test_bulk_update_only_touches_specified_fields(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client, "BulkPartialBucket")
        sub = await _create_sub(client, bid, name="Untouched", amount=5.0)

        resp = await client.patch(
            f"/api/buckets/{bid}/subscriptions/bulk",
            json={"ids": [sub["id"]], "update": {"amount": 42.0}},
        )
        assert resp.status_code == 200

        get_resp = await client.get(f"/api/buckets/{bid}/subscriptions/{sub['id']}")
        body = get_resp.json()
        assert body["amount"] == pytest.approx(42.0)
        assert body["name"] == "Untouched"

    async def test_bulk_update_explicit_null_clears_field(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client, "BulkClearBucket")
        sub = await _create_sub(client, bid, category="Streaming")
        assert sub["category_name"] == "Streaming"

        resp = await client.patch(
            f"/api/buckets/{bid}/subscriptions/bulk",
            json={"ids": [sub["id"]], "update": {"category_name": None}},
        )
        assert resp.status_code == 200

        get_resp = await client.get(f"/api/buckets/{bid}/subscriptions/{sub['id']}")
        assert get_resp.json()["category_name"] is None

    async def test_bulk_update_records_history_per_record(
        self, client: AsyncClient
    ) -> None:
        bid = await _create_bucket(client, "BulkHistoryBucket")
        sub1 = await _create_sub(client, bid, name="A", amount=5.0)
        sub2 = await _create_sub(client, bid, name="B", amount=5.0)

        await client.patch(
            f"/api/buckets/{bid}/subscriptions/bulk",
            json={"ids": [sub1["id"], sub2["id"]], "update": {"amount": 9.0}},
        )

        for sub_id in (sub1["id"], sub2["id"]):
            hist_resp = await client.get(
                f"/api/buckets/{bid}/subscriptions/{sub_id}/history"
            )
            entries = hist_resp.json()
            assert len(entries) == 1
            assert entries[0]["field"] == "amount"
            assert entries[0]["old_value"] == "5.0"
            assert entries[0]["new_value"] == "9.0"

    async def test_bulk_update_owner_name(self, client: AsyncClient) -> None:
        bid = await _create_bucket(client, "BulkOwnerBucket")
        sub = await _create_sub(client, bid)

        resp = await client.patch(
            f"/api/buckets/{bid}/subscriptions/bulk",
            json={"ids": [sub["id"]], "update": {"owner_name": "Alex"}},
        )
        assert resp.status_code == 200

        get_resp = await client.get(f"/api/buckets/{bid}/subscriptions/{sub['id']}")
        assert get_resp.json()["owner_name"] == "Alex"

    async def test_bulk_update_rejects_id_from_another_bucket(
        self, client: AsyncClient
    ) -> None:
        bid1 = await _create_bucket(client, "BulkCrossA")
        bid2 = await _create_bucket(client, "BulkCrossB")
        sub_in_other_bucket = await _create_sub(client, bid2, amount=5.0)

        resp = await client.patch(
            f"/api/buckets/{bid1}/subscriptions/bulk",
            json={"ids": [sub_in_other_bucket["id"]], "update": {"amount": 99.0}},
        )
        assert resp.status_code == 404

        # Confirm nothing was committed — the record is untouched.
        get_resp = await client.get(
            f"/api/buckets/{bid2}/subscriptions/{sub_in_other_bucket['id']}"
        )
        assert get_resp.json()["amount"] == pytest.approx(5.0)


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

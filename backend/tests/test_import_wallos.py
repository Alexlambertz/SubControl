"""
Tests for the Wallos import service and endpoint.
"""

from __future__ import annotations

import json
import pytest
import respx
import httpx
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Unit tests for the parsing / normalisation helpers
# ---------------------------------------------------------------------------


class TestWallosIntervalNormalisation:
    def _norm(self, v):
        from backend.services.wallos_import import _normalise_interval
        return _normalise_interval(v)

    def test_monthly(self):        assert self._norm("monthly") == "monthly"
    def test_yearly(self):         assert self._norm("yearly") == "yearly"
    def test_annually(self):       assert self._norm("annually") == "yearly"
    def test_weekly(self):         assert self._norm("weekly") == "weekly"
    def test_daily(self):          assert self._norm("daily") == "daily"
    def test_quarterly(self):      assert self._norm("quarterly") == "quarterly"
    def test_half_yearly(self):    assert self._norm("half-yearly") == "half-year"
    def test_biannually(self):     assert self._norm("biannually") == "half-year"
    def test_case_insensitive(self): assert self._norm("MONTHLY") == "monthly"
    def test_unknown_returns_none(self): assert self._norm("every-other-thursday") is None
    def test_none_returns_none(self):   assert self._norm(None) is None


class TestParseSubscription:
    def _parse(self, d):
        from backend.services.wallos_import import _parse_subscription
        return _parse_subscription(d)

    def test_minimal_valid(self):
        sub = self._parse({
            "name": "Netflix",
            "price": 12.99,
            "currency_id": "EUR",
            "payment_cycle": "monthly",
        })
        assert sub["name"] == "Netflix"
        assert sub["amount"] == pytest.approx(12.99)
        assert sub["currency"] == "EUR"
        assert sub["recurring_interval"] == "monthly"
        assert sub["recurring_date"] is None

    def test_next_payment_date_converted_to_last_payment(self):
        """next_payment_date should be converted to last_payment_date by subtracting one interval."""
        sub = self._parse({
            "name": "Spotify",
            "price": 9.99,
            "currency_id": "EUR",
            "payment_cycle": "monthly",
            "next_payment_date": "2025-07-01",
        })
        # monthly: next 2025-07-01 → last payment 2025-06-01
        assert sub["recurring_date"] == "2025-06-01"

    def test_last_payment_date_preferred_over_next(self):
        """If last_payment_date is provided, it takes precedence over next_payment_date."""
        sub = self._parse({
            "name": "Spotify",
            "price": 9.99,
            "currency_id": "EUR",
            "payment_cycle": "monthly",
            "last_payment_date": "2025-06-01",
            "next_payment_date": "2025-07-01",
        })
        assert sub["recurring_date"] == "2025-06-01"

    def test_category_name_direct(self):
        sub = self._parse({
            "name": "X",
            "price": 1,
            "currency_id": "USD",
            "payment_cycle": "yearly",
            "category_name": "Entertainment",
        })
        assert sub["category_name"] == "Entertainment"

    def test_category_nested_dict(self):
        sub = self._parse({
            "name": "X",
            "price": 1,
            "currency_id": "USD",
            "payment_cycle": "yearly",
            "category": {"id": 3, "name": "Software"},
        })
        assert sub["category_name"] == "Software"

    def test_half_yearly_mapped(self):
        sub = self._parse({
            "name": "X",
            "price": 5,
            "currency_id": "EUR",
            "payment_cycle": "half-yearly",
        })
        assert sub["recurring_interval"] == "half-year"

    def test_missing_name_raises(self):
        with pytest.raises(ValueError, match="no name"):
            self._parse({"price": 5, "currency_id": "EUR", "payment_cycle": "monthly"})

    def test_bad_price_raises(self):
        with pytest.raises(ValueError, match="price"):
            self._parse({"name": "X", "price": "abc", "currency_id": "EUR", "payment_cycle": "monthly"})

    def test_unknown_cycle_raises(self):
        with pytest.raises(ValueError, match="unsupported payment_cycle"):
            self._parse({"name": "X", "price": 5, "currency_id": "EUR", "payment_cycle": "fortnightly"})


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


WALLOS_URL = "https://wallos.example.com"

WALLOS_RESPONSE = {
    "success": True,
    "subscriptions": [
        {
            "name": "Netflix",
            "price": 12.99,
            "currency_id": "EUR",
            "payment_cycle": "monthly",
            "next_payment_date": "2025-06-15",
            "category_name": "Streaming",
            "inactive": 0,
        },
        {
            "name": "Adobe CC",
            "price": 60.00,
            "currency_id": "USD",
            "payment_cycle": "yearly",
            "next_payment_date": "2026-01-01",
            "category_name": "Software",
            "inactive": 0,
        },
        {
            "name": "OldSub",
            "price": 5.00,
            "currency_id": "EUR",
            "payment_cycle": "monthly",
            "inactive": 1,
        },
    ],
}


class TestWallosEndpoint:
    async def test_import_creates_subscriptions(self, client: AsyncClient):
        bucket = await client.post("/api/buckets", json={"name": "WallosBucket"})
        bucket_id = bucket.json()["id"]

        with respx.mock:
            respx.get(f"{WALLOS_URL}/api/subscriptions").mock(
                return_value=httpx.Response(200, json=WALLOS_RESPONSE)
            )
            res = await client.post(
                "/api/import/wallos",
                json={"url": WALLOS_URL, "api_key": "tok123", "bucket_id": bucket_id},
            )

        assert res.status_code == 200
        body = res.json()
        assert body["imported"] == 2   # OldSub is inactive → skipped
        assert body["skipped"] == 1
        assert body["failed"] == []

        subs = await client.get(f"/api/buckets/{bucket_id}/subscriptions")
        names = [s["name"] for s in subs.json()]
        assert "Netflix" in names
        assert "Adobe CC" in names
        assert "OldSub" not in names

    async def test_include_inactive_when_flag_false(self, client: AsyncClient):
        bucket = await client.post("/api/buckets", json={"name": "WallosAll"})
        bucket_id = bucket.json()["id"]

        with respx.mock:
            respx.get(f"{WALLOS_URL}/api/subscriptions").mock(
                return_value=httpx.Response(200, json=WALLOS_RESPONSE)
            )
            res = await client.post(
                "/api/import/wallos",
                json={
                    "url": WALLOS_URL,
                    "api_key": "tok",
                    "bucket_id": bucket_id,
                    "skip_inactive": False,
                },
            )

        assert res.json()["imported"] == 3
        assert res.json()["skipped"] == 0

    async def test_nonexistent_bucket_returns_404(self, client: AsyncClient):
        with respx.mock:
            res = await client.post(
                "/api/import/wallos",
                json={
                    "url": WALLOS_URL,
                    "api_key": "tok",
                    "bucket_id": "00000000000000000000000000000099",
                },
            )
        assert res.status_code == 404

    async def test_wallos_unreachable_returns_422(self, client: AsyncClient):
        bucket = await client.post("/api/buckets", json={"name": "WallosDown"})
        bucket_id = bucket.json()["id"]

        with respx.mock:
            respx.get(f"{WALLOS_URL}/api/subscriptions").mock(
                side_effect=httpx.ConnectError("refused")
            )
            res = await client.post(
                "/api/import/wallos",
                json={"url": WALLOS_URL, "api_key": "tok", "bucket_id": bucket_id},
            )

        assert res.status_code == 422
        assert "reach" in res.json()["detail"].lower()

    async def test_wallos_api_error_status_returns_422(self, client: AsyncClient):
        bucket = await client.post("/api/buckets", json={"name": "WallosErr"})
        bucket_id = bucket.json()["id"]

        with respx.mock:
            respx.get(f"{WALLOS_URL}/api/subscriptions").mock(
                return_value=httpx.Response(401, text="Unauthorized")
            )
            res = await client.post(
                "/api/import/wallos",
                json={"url": WALLOS_URL, "api_key": "bad-key", "bucket_id": bucket_id},
            )

        assert res.status_code == 422
        assert "401" in res.json()["detail"]

    async def test_partial_failure_reported(self, client: AsyncClient):
        """A subscription with an unknown payment_cycle appears in failed[]."""
        bucket = await client.post("/api/buckets", json={"name": "WallosPartial"})
        bucket_id = bucket.json()["id"]

        payload = {
            "success": True,
            "subscriptions": [
                {"name": "Good", "price": 5, "currency_id": "EUR",
                 "payment_cycle": "monthly", "inactive": 0},
                {"name": "Bad", "price": 5, "currency_id": "EUR",
                 "payment_cycle": "fortnightly", "inactive": 0},
            ],
        }

        with respx.mock:
            respx.get(f"{WALLOS_URL}/api/subscriptions").mock(
                return_value=httpx.Response(200, json=payload)
            )
            res = await client.post(
                "/api/import/wallos",
                json={"url": WALLOS_URL, "api_key": "tok", "bucket_id": bucket_id},
            )

        body = res.json()
        assert body["imported"] == 1
        assert len(body["failed"]) == 1
        assert body["failed"][0]["name"] == "Bad"

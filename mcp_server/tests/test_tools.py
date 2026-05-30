"""
Tests for MCP server tool handlers.

Uses respx to mock HTTP calls to the SubControl API.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx


_BUCKET = {"id": "bucket-1", "name": "Home", "created_at": "2024-01-01T00:00:00"}
_SUB = {
    "id": "sub-1",
    "bucket_id": "bucket-1",
    "name": "Netflix",
    "provider_name": "Netflix",
    "recurring_interval": "monthly",
    "recurring_date": "2024-01-15",
    "amount": 9.99,
    "currency": "EUR",
    "image_url": None,
    "category_name": "Streaming",
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
}


class TestListBuckets:
    @respx.mock
    async def test_returns_bucket_list(self) -> None:
        from mcp_server.tools import list_buckets

        respx.get("http://localhost:8000/api/buckets").mock(
            return_value=httpx.Response(200, json=[_BUCKET])
        )
        result = await list_buckets()
        assert len(result) == 1
        assert result[0]["name"] == "Home"


class TestListSubscriptions:
    @respx.mock
    async def test_with_bucket_id(self) -> None:
        from mcp_server.tools import list_subscriptions

        respx.get(
            "http://localhost:8000/api/buckets/bucket-1/subscriptions"
        ).mock(return_value=httpx.Response(200, json=[_SUB]))

        result = await list_subscriptions(bucket_id="bucket-1")
        assert result[0]["name"] == "Netflix"

    @respx.mock
    async def test_without_bucket_id_aggregates_all_buckets(self) -> None:
        from mcp_server.tools import list_subscriptions

        respx.get("http://localhost:8000/api/buckets").mock(
            return_value=httpx.Response(200, json=[_BUCKET])
        )
        respx.get(
            "http://localhost:8000/api/buckets/bucket-1/subscriptions"
        ).mock(return_value=httpx.Response(200, json=[_SUB]))

        result = await list_subscriptions()
        assert len(result) == 1


class TestGetSubscription:
    @respx.mock
    async def test_returns_subscription(self) -> None:
        from mcp_server.tools import get_subscription

        respx.get(
            "http://localhost:8000/api/buckets/bucket-1/subscriptions/sub-1"
        ).mock(return_value=httpx.Response(200, json=_SUB))

        result = await get_subscription("sub-1", "bucket-1")
        assert result["id"] == "sub-1"


class TestCreateSubscription:
    @respx.mock
    async def test_creates_subscription(self) -> None:
        from mcp_server.tools import create_subscription

        respx.post(
            "http://localhost:8000/api/buckets/bucket-1/subscriptions"
        ).mock(return_value=httpx.Response(201, json=_SUB))

        result = await create_subscription(
            bucket_id="bucket-1",
            name="Netflix",
            provider_name="Netflix",
            recurring_interval="monthly",
            recurring_date="2024-01-15",
            amount=9.99,
        )
        assert result["name"] == "Netflix"


class TestUpdateSubscription:
    @respx.mock
    async def test_updates_subscription(self) -> None:
        from mcp_server.tools import update_subscription

        updated = {**_SUB, "amount": 14.99}
        respx.put(
            "http://localhost:8000/api/buckets/bucket-1/subscriptions/sub-1"
        ).mock(return_value=httpx.Response(200, json=updated))

        result = await update_subscription("sub-1", "bucket-1", amount=14.99)
        assert result["amount"] == 14.99


class TestDeleteSubscription:
    @respx.mock
    async def test_deletes_subscription(self) -> None:
        from mcp_server.tools import delete_subscription

        respx.delete(
            "http://localhost:8000/api/buckets/bucket-1/subscriptions/sub-1"
        ).mock(return_value=httpx.Response(204))

        result = await delete_subscription("sub-1", "bucket-1")
        assert result["deleted"] is True


class TestGetDashboardSummary:
    @respx.mock
    async def test_average_mode(self) -> None:
        from mcp_server.tools import get_dashboard_summary

        summary = {
            "total_monthly": 9.99,
            "subscriptions": [{"name": "Netflix", "monthly_amount": 9.99, "currency": "EUR"}],
            "by_category": [{"category": "Streaming", "total": 9.99}],
        }
        respx.get("http://localhost:8000/api/dashboard").mock(
            return_value=httpx.Response(200, json=summary)
        )

        result = await get_dashboard_summary(mode="average")
        assert result["total_monthly"] == 9.99

    @respx.mock
    async def test_http_error_propagates_as_exception(self) -> None:
        from mcp_server.tools import get_dashboard_summary

        respx.get("http://localhost:8000/api/dashboard").mock(
            return_value=httpx.Response(500, json={"detail": "server error"})
        )

        with pytest.raises(httpx.HTTPStatusError):
            await get_dashboard_summary()

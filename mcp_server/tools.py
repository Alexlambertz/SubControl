"""
MCP tool handler functions for SubControl.

Each function corresponds to one MCP tool and delegates to the REST API
via :mod:`mcp_server.client`.

Tools
-----
list_subscriptions      List subscriptions, optionally filtered.
get_subscription        Get a single subscription by ID.
create_subscription     Create a new subscription in a bucket.
update_subscription     Update fields of an existing subscription.
delete_subscription     Delete a subscription.
list_buckets            List all available buckets.
get_dashboard_summary   Get spending summary for a mode/month.
"""

from __future__ import annotations

from typing import Any, Optional

from mcp_server import client as api


async def list_subscriptions(
    bucket_id: Optional[str] = None,
    category_id: Optional[int] = None,
    provider_id: Optional[int] = None,
) -> Any:
    """List subscriptions.  Optionally filter by bucket_id or category_id."""
    params: dict = {}
    if bucket_id:
        # Subscriptions are scoped to a bucket in the API
        return await api.api_get(f"/api/buckets/{bucket_id}/subscriptions")
    # If no bucket_id: fetch all buckets first, then aggregate
    buckets = await api.api_get("/api/buckets")
    all_subs = []
    for bucket in buckets:
        subs = await api.api_get(f"/api/buckets/{bucket['id']}/subscriptions")
        all_subs.extend(subs)
    if category_id is not None:
        all_subs = [s for s in all_subs if s.get("category_id") == category_id]
    return all_subs


async def get_subscription(subscription_id: str, bucket_id: str) -> Any:
    """Return a single subscription."""
    return await api.api_get(
        f"/api/buckets/{bucket_id}/subscriptions/{subscription_id}"
    )


async def create_subscription(
    bucket_id: str,
    name: str,
    provider_name: str,
    recurring_interval: str,
    recurring_date: str,
    amount: float,
    currency: str = "EUR",
    category_name: Optional[str] = None,
) -> Any:
    """Create a new subscription in the given bucket."""
    body: dict = {
        "name": name,
        "provider_name": provider_name,
        "recurring_interval": recurring_interval,
        "recurring_date": recurring_date,
        "amount": amount,
        "currency": currency,
    }
    if category_name:
        body["category_name"] = category_name
    return await api.api_post(f"/api/buckets/{bucket_id}/subscriptions", body)


async def update_subscription(
    subscription_id: str,
    bucket_id: str,
    name: Optional[str] = None,
    provider_name: Optional[str] = None,
    recurring_interval: Optional[str] = None,
    recurring_date: Optional[str] = None,
    amount: Optional[float] = None,
    currency: Optional[str] = None,
    category_name: Optional[str] = None,
) -> Any:
    """Update one or more fields of an existing subscription."""
    body: dict = {}
    if name is not None:
        body["name"] = name
    if provider_name is not None:
        body["provider_name"] = provider_name
    if recurring_interval is not None:
        body["recurring_interval"] = recurring_interval
    if recurring_date is not None:
        body["recurring_date"] = recurring_date
    if amount is not None:
        body["amount"] = amount
    if currency is not None:
        body["currency"] = currency
    if category_name is not None:
        body["category_name"] = category_name
    return await api.api_put(
        f"/api/buckets/{bucket_id}/subscriptions/{subscription_id}", body
    )


async def delete_subscription(subscription_id: str, bucket_id: str) -> Any:
    """Delete a subscription."""
    return await api.api_delete(
        f"/api/buckets/{bucket_id}/subscriptions/{subscription_id}"
    )


async def list_buckets() -> Any:
    """Return all available buckets."""
    return await api.api_get("/api/buckets")


async def get_dashboard_summary(
    mode: str = "average",
    month: Optional[str] = None,
    bucket_id: Optional[str] = None,
) -> Any:
    """
    Return the spending dashboard summary.

    Parameters
    ----------
    mode:    "average" (default) or "real"
    month:   YYYY-MM — required when mode="real"
    bucket_id: Optional filter to a single bucket.
    """
    params: dict = {"mode": mode}
    if month:
        params["month"] = month
    if bucket_id:
        params["bucket_id"] = bucket_id
    return await api.api_get("/api/dashboard", params=params)

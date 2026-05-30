"""
Subscriptions router — CRUD for subscriptions within a bucket.

Routes
------
GET    /api/buckets/{bucket_id}/subscriptions              List subscriptions
POST   /api/buckets/{bucket_id}/subscriptions              Create subscription
GET    /api/buckets/{bucket_id}/subscriptions/{sub_id}     Get single subscription
PUT    /api/buckets/{bucket_id}/subscriptions/{sub_id}     Update subscription
DELETE /api/buckets/{bucket_id}/subscriptions/{sub_id}     Delete subscription

Provider and Category records are created on-the-fly when a new name is supplied.
Logo URLs are fetched asynchronously after create/update (fire-and-forget).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

from backend.database import get_db
from backend.dependencies import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["subscriptions"])

VALID_INTERVALS = {"daily", "weekly", "monthly", "quarterly", "half-year", "yearly"}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SubscriptionCreate(BaseModel):
    name: str
    provider_name: str
    recurring_interval: str
    recurring_date: Optional[str] = None
    end_date: Optional[str] = None
    amount: float = 0.0
    currency: str = "EUR"
    category_name: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Subscription name must not be empty")
        return v.strip()

    @field_validator("recurring_interval")
    @classmethod
    def valid_interval(cls, v: str) -> str:
        if v not in VALID_INTERVALS:
            raise ValueError(
                f"recurring_interval must be one of {sorted(VALID_INTERVALS)}"
            )
        return v


class SubscriptionUpdate(BaseModel):
    name: Optional[str] = None
    provider_name: Optional[str] = None
    recurring_interval: Optional[str] = None
    recurring_date: Optional[str] = None
    end_date: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    category_name: Optional[str] = None
    image_url: Optional[str] = None

    @field_validator("recurring_interval")
    @classmethod
    def valid_interval(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_INTERVALS:
            raise ValueError(
                f"recurring_interval must be one of {sorted(VALID_INTERVALS)}"
            )
        return v


class SubscriptionResponse(BaseModel):
    id: str
    bucket_id: str
    name: str
    provider_name: Optional[str] = None
    recurring_interval: str
    recurring_date: Optional[str] = None
    end_date: Optional[str] = None
    amount: float
    currency: str
    image_url: Optional[str] = None
    category_name: Optional[str] = None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_bucket_or_404(bucket_id: str, db: aiosqlite.Connection) -> None:
    async with db.execute("SELECT id FROM buckets WHERE id = ?", (bucket_id,)) as cur:
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Bucket not found")


async def _get_sub_or_404(
    bucket_id: str, sub_id: str, db: aiosqlite.Connection
) -> dict:
    async with db.execute(
        """
        SELECT s.id, s.bucket_id, s.name,
               p.name AS provider_name,
               s.recurring_interval, s.recurring_date, s.end_date,
               s.amount, s.currency, s.image_url,
               c.name AS category_name,
               s.created_at, s.updated_at
        FROM subscriptions s
        LEFT JOIN providers p ON s.provider_id = p.id
        LEFT JOIN categories c ON s.category_id = c.id
        WHERE s.id = ? AND s.bucket_id = ?
        """,
        (sub_id, bucket_id),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return dict(row)


async def _get_or_create_provider(
    name: str, db: aiosqlite.Connection
) -> int:
    """Return the provider ID, creating it if it doesn't exist."""
    async with db.execute(
        "SELECT id FROM providers WHERE name = ?", (name,)
    ) as cur:
        row = await cur.fetchone()
    if row:
        return row["id"]
    async with db.execute(
        "INSERT INTO providers (name) VALUES (?) RETURNING id", (name,)
    ) as cur:
        row = await cur.fetchone()
    await db.commit()
    return row["id"]


async def _get_or_create_category(
    name: str, db: aiosqlite.Connection
) -> int:
    """Return the category ID, creating it if it doesn't exist."""
    async with db.execute(
        "SELECT id FROM categories WHERE name = ?", (name,)
    ) as cur:
        row = await cur.fetchone()
    if row:
        return row["id"]
    async with db.execute(
        "INSERT INTO categories (name) VALUES (?) RETURNING id", (name,)
    ) as cur:
        row = await cur.fetchone()
    await db.commit()
    return row["id"]


async def _update_logo(sub_id: str, provider_name: str, db_path: str) -> None:
    """
    Background task: fetch logo for *provider_name* and persist in *sub_id*.
    Uses a fresh connection so it doesn't interfere with the request connection.
    """
    from backend.services.logo_fetch import fetch_logo_url

    url = await fetch_logo_url(provider_name)
    if url:
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                "UPDATE subscriptions SET image_url = ? WHERE id = ?",
                (url, sub_id),
            )
            await conn.commit()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/api/buckets/{bucket_id}/subscriptions",
    response_model=list[SubscriptionResponse],
)
async def list_subscriptions(
    bucket_id: str,
    _user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[SubscriptionResponse]:
    await _get_bucket_or_404(bucket_id, db)
    async with db.execute(
        """
        SELECT s.id, s.bucket_id, s.name,
               p.name AS provider_name,
               s.recurring_interval, s.recurring_date, s.end_date,
               s.amount, s.currency, s.image_url,
               c.name AS category_name,
               s.created_at, s.updated_at
        FROM subscriptions s
        LEFT JOIN providers p ON s.provider_id = p.id
        LEFT JOIN categories c ON s.category_id = c.id
        WHERE s.bucket_id = ?
        ORDER BY s.name
        """,
        (bucket_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [SubscriptionResponse(**dict(r)) for r in rows]


@router.post(
    "/api/buckets/{bucket_id}/subscriptions",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_subscription(
    bucket_id: str,
    body: SubscriptionCreate,
    _user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> SubscriptionResponse:
    await _get_bucket_or_404(bucket_id, db)

    provider_id = await _get_or_create_provider(body.provider_name, db)
    category_id = (
        await _get_or_create_category(body.category_name, db)
        if body.category_name
        else None
    )

    async with db.execute(
        """
        INSERT INTO subscriptions
            (bucket_id, name, provider_id, recurring_interval, recurring_date,
             end_date, amount, currency, category_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id, bucket_id, name, recurring_interval, recurring_date,
                  end_date, amount, currency, image_url, created_at, updated_at
        """,
        (
            bucket_id,
            body.name,
            provider_id,
            body.recurring_interval,
            body.recurring_date,
            body.end_date,
            body.amount,
            body.currency,
            category_id,
        ),
    ) as cur:
        row = await cur.fetchone()
    await db.commit()

    sub_id = row["id"]

    # Fire-and-forget logo fetch
    from backend.database import get_db_path
    asyncio.create_task(
        _update_logo(sub_id, body.provider_name, get_db_path())
    )

    return SubscriptionResponse(
        **dict(row),
        provider_name=body.provider_name,
        category_name=body.category_name,
    )


@router.get(
    "/api/buckets/{bucket_id}/subscriptions/{sub_id}",
    response_model=SubscriptionResponse,
)
async def get_subscription(
    bucket_id: str,
    sub_id: str,
    _user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> SubscriptionResponse:
    return SubscriptionResponse(**await _get_sub_or_404(bucket_id, sub_id, db))


@router.put(
    "/api/buckets/{bucket_id}/subscriptions/{sub_id}",
    response_model=SubscriptionResponse,
)
async def update_subscription(
    bucket_id: str,
    sub_id: str,
    body: SubscriptionUpdate,
    _user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> SubscriptionResponse:
    existing = await _get_sub_or_404(bucket_id, sub_id, db)

    # Resolve provider
    provider_id: Optional[int] = None
    if body.provider_name is not None:
        provider_id = await _get_or_create_provider(body.provider_name, db)
    else:
        # Keep existing provider
        async with db.execute(
            "SELECT provider_id FROM subscriptions WHERE id = ?", (sub_id,)
        ) as cur:
            prow = await cur.fetchone()
        provider_id = prow["provider_id"] if prow else None

    # Resolve category
    category_id: Optional[int] = None
    if body.category_name is not None:
        category_id = await _get_or_create_category(body.category_name, db)
    else:
        async with db.execute(
            "SELECT category_id FROM subscriptions WHERE id = ?", (sub_id,)
        ) as cur:
            crow = await cur.fetchone()
        category_id = crow["category_id"] if crow else None

    updates = {
        "name": body.name if body.name is not None else existing["name"],
        "provider_id": provider_id,
        "recurring_interval": (
            body.recurring_interval
            if body.recurring_interval is not None
            else existing["recurring_interval"]
        ),
        "recurring_date": (
            body.recurring_date
            if body.recurring_date is not None
            else existing["recurring_date"]
        ),
        "end_date": (
            body.end_date
            if body.end_date is not None
            else existing.get("end_date")
        ),
        "amount": body.amount if body.amount is not None else existing["amount"],
        "currency": body.currency if body.currency is not None else existing["currency"],
        "category_id": category_id,
        "image_url": body.image_url if body.image_url is not None else existing.get("image_url"),
    }

    await db.execute(
        """
        UPDATE subscriptions
        SET name = :name, provider_id = :provider_id,
            recurring_interval = :recurring_interval,
            recurring_date = :recurring_date, end_date = :end_date,
            amount = :amount, currency = :currency,
            category_id = :category_id, image_url = :image_url
        WHERE id = :id
        """,
        {**updates, "id": sub_id},
    )
    await db.commit()

    # Fire-and-forget logo refresh if provider changed
    if body.provider_name is not None:
        from backend.database import get_db_path
        asyncio.create_task(
            _update_logo(sub_id, body.provider_name, get_db_path())
        )

    return SubscriptionResponse(**await _get_sub_or_404(bucket_id, sub_id, db))


@router.delete(
    "/api/buckets/{bucket_id}/subscriptions/{sub_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_subscription(
    bucket_id: str,
    sub_id: str,
    _user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> None:
    await _get_sub_or_404(bucket_id, sub_id, db)
    await db.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
    await db.commit()

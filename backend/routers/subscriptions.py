"""
Subscriptions router — CRUD for subscriptions within a bucket, plus
attachment upload/download/delete (e.g. a signup confirmation or renewal
letter).

Routes
------
GET    /api/buckets/{bucket_id}/subscriptions                                  List subscriptions
POST   /api/buckets/{bucket_id}/subscriptions                                  Create subscription
GET    /api/buckets/{bucket_id}/subscriptions/{sub_id}                         Get single subscription
PUT    /api/buckets/{bucket_id}/subscriptions/{sub_id}                         Update subscription
DELETE /api/buckets/{bucket_id}/subscriptions/{sub_id}                         Delete subscription
POST   /api/buckets/{bucket_id}/subscriptions/{sub_id}/attachments             Upload attachment
GET    /api/buckets/{bucket_id}/subscriptions/{sub_id}/attachments/{id}        Download attachment
DELETE /api/buckets/{bucket_id}/subscriptions/{sub_id}/attachments/{id}        Delete attachment

Provider and Category records are created on-the-fly when a new name is supplied.
Logo URLs are fetched asynchronously after create/update (fire-and-forget).
Every attachment upload is best-effort analyzed by AI and compared against
the subscription's current field values (see analyze_attachment_for_updates
in services/ai_extract.py) — analysis never blocks the upload itself.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, field_validator

from backend.database import get_db
from backend.dependencies import CurrentUser, get_current_user
from backend.services.ai_extract import analyze_attachment_for_updates
from backend.services.attachments import (
    attachments_dir,
    delete_attachment_file,
    save_attachment,
)
from backend.services.history import (
    SUBSCRIPTION_HISTORY_FIELDS,
    HistoryEntryResponse,
    get_history,
    record_changes,
)

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


class AttachmentResponse(BaseModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: str


class AttachmentUploadResult(BaseModel):
    attachment: AttachmentResponse
    suggested_updates: dict[str, Any] = {}


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
    attachments: list[AttachmentResponse] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_bucket_or_404(bucket_id: str, db: aiosqlite.Connection) -> None:
    async with db.execute("SELECT id FROM buckets WHERE id = ?", (bucket_id,)) as cur:
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Bucket not found")


async def _check_bucket_access(
    bucket_id: str, user: "CurrentUser", db: aiosqlite.Connection
) -> None:
    """Raise 403 if *user* is not assigned to *bucket_id* (admins always pass)."""
    if user.is_admin:
        return
    async with db.execute(
        "SELECT 1 FROM user_buckets WHERE user_id = ? AND bucket_id = ?",
        (user.id, bucket_id),
    ) as cur:
        if await cur.fetchone() is None:
            raise HTTPException(status_code=403, detail="Access denied to this bucket")


async def _get_sub_or_404(
    bucket_id: str, sub_id: str, db: aiosqlite.Connection
) -> dict:
    async with db.execute(
        """
        SELECT s.id, s.bucket_id, s.name,
               s.provider_id, p.name AS provider_name,
               s.recurring_interval, s.recurring_date, s.end_date,
               s.amount, s.currency, s.image_url,
               s.category_id, c.name AS category_name,
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


async def _get_attachments(sub_id: str, db: aiosqlite.Connection) -> list[dict]:
    async with db.execute(
        """
        SELECT id, filename, content_type, size_bytes, uploaded_at
        FROM subscription_attachments
        WHERE subscription_id = ?
        ORDER BY uploaded_at
        """,
        (sub_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def _get_attachment_or_404(
    sub_id: str, attachment_id: str, db: aiosqlite.Connection
) -> dict:
    async with db.execute(
        """
        SELECT id, subscription_id, filename, content_type, size_bytes, storage_path, uploaded_at
        FROM subscription_attachments
        WHERE id = ? AND subscription_id = ?
        """,
        (attachment_id, sub_id),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
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
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[SubscriptionResponse]:
    await _get_bucket_or_404(bucket_id, db)
    await _check_bucket_access(bucket_id, user, db)
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
        rows = [dict(r) for r in await cur.fetchall()]

    # Fetch attachments for every subscription in one query, then group in
    # Python instead of issuing one query per subscription.
    attachments_by_sub: dict[str, list[dict]] = {}
    if rows:
        async with db.execute(
            """
            SELECT a.id, a.subscription_id, a.filename, a.content_type, a.size_bytes, a.uploaded_at
            FROM subscription_attachments a
            JOIN subscriptions s ON a.subscription_id = s.id
            WHERE s.bucket_id = ?
            ORDER BY a.uploaded_at
            """,
            (bucket_id,),
        ) as cur:
            for a in await cur.fetchall():
                attachments_by_sub.setdefault(a["subscription_id"], []).append(dict(a))

    return [
        SubscriptionResponse(**r, attachments=attachments_by_sub.get(r["id"], []))
        for r in rows
    ]


@router.post(
    "/api/buckets/{bucket_id}/subscriptions",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_subscription(
    bucket_id: str,
    body: SubscriptionCreate,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> SubscriptionResponse:
    await _get_bucket_or_404(bucket_id, db)
    await _check_bucket_access(bucket_id, user, db)

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
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> SubscriptionResponse:
    await _check_bucket_access(bucket_id, user, db)
    existing = await _get_sub_or_404(bucket_id, sub_id, db)
    attachments = await _get_attachments(sub_id, db)
    return SubscriptionResponse(**existing, attachments=attachments)


@router.put(
    "/api/buckets/{bucket_id}/subscriptions/{sub_id}",
    response_model=SubscriptionResponse,
)
async def update_subscription(
    bucket_id: str,
    sub_id: str,
    body: SubscriptionUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> SubscriptionResponse:
    await _check_bucket_access(bucket_id, user, db)
    existing = await _get_sub_or_404(bucket_id, sub_id, db)

    # Fields the client actually sent (present in the JSON body, even if the
    # value is null) — vs. fields simply omitted. A cleared date/category is
    # sent as an explicit null; distinguishing the two is required to tell
    # "clear this field" apart from "leave it alone" (both look like `None`
    # once parsed, since Optional[...] fields default to None either way).
    fields_set = body.model_fields_set

    # Resolve provider — reuse the id already fetched by _get_sub_or_404
    # instead of re-querying the row we just read.
    provider_id: Optional[int] = (
        await _get_or_create_provider(body.provider_name, db)
        if body.provider_name is not None
        else existing["provider_id"]
    )

    # Resolve category — same reuse, but a cleared (null) category must
    # actually clear category_id rather than falling back to existing.
    if "category_name" in fields_set:
        category_id: Optional[int] = (
            await _get_or_create_category(body.category_name, db)
            if body.category_name
            else None
        )
    else:
        category_id = existing["category_id"]

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
            if "recurring_date" in fields_set
            else existing["recurring_date"]
        ),
        "end_date": (
            body.end_date
            if "end_date" in fields_set
            else existing.get("end_date")
        ),
        "amount": body.amount if body.amount is not None else existing["amount"],
        "currency": body.currency if body.currency is not None else existing["currency"],
        "category_id": category_id,
        "image_url": body.image_url if body.image_url is not None else existing.get("image_url"),
    }

    # Human-readable versions of the same resolved values, for the change
    # history log (the SQL updates above use internal FK ids instead).
    new_display_values = {
        "name": updates["name"],
        "provider_name": (
            body.provider_name if body.provider_name is not None else existing["provider_name"]
        ),
        "recurring_interval": updates["recurring_interval"],
        "recurring_date": updates["recurring_date"],
        "end_date": updates["end_date"],
        "amount": updates["amount"],
        "currency": updates["currency"],
        "category_name": (
            body.category_name if "category_name" in fields_set else existing["category_name"]
        ),
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
    await record_changes(
        db,
        table="subscription_history",
        id_column="subscription_id",
        entity_id=sub_id,
        old_values=existing,
        new_values=new_display_values,
        fields=SUBSCRIPTION_HISTORY_FIELDS,
        user=user,
    )
    await db.commit()

    # Fire-and-forget logo refresh if provider changed
    if body.provider_name is not None:
        from backend.database import get_db_path
        asyncio.create_task(
            _update_logo(sub_id, body.provider_name, get_db_path())
        )

    refreshed = await _get_sub_or_404(bucket_id, sub_id, db)
    attachments = await _get_attachments(sub_id, db)
    return SubscriptionResponse(**refreshed, attachments=attachments)


@router.delete(
    "/api/buckets/{bucket_id}/subscriptions/{sub_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_subscription(
    bucket_id: str,
    sub_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> None:
    await _check_bucket_access(bucket_id, user, db)
    await _get_sub_or_404(bucket_id, sub_id, db)

    async with db.execute(
        "SELECT storage_path FROM subscription_attachments WHERE subscription_id = ?",
        (sub_id,),
    ) as cur:
        storage_paths = [r["storage_path"] for r in await cur.fetchall()]

    # ON DELETE CASCADE removes the subscription_attachments rows; delete the
    # underlying files afterward so a failed unlink doesn't block the DB delete.
    await db.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
    await db.commit()

    for path in storage_paths:
        delete_attachment_file(path)


# ---------------------------------------------------------------------------
# Routes — attachments
# ---------------------------------------------------------------------------


@router.post(
    "/api/buckets/{bucket_id}/subscriptions/{sub_id}/attachments",
    response_model=AttachmentUploadResult,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    bucket_id: str,
    sub_id: str,
    file: UploadFile,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> AttachmentUploadResult:
    await _check_bucket_access(bucket_id, user, db)
    existing = await _get_sub_or_404(bucket_id, sub_id, db)

    storage_path, filename, size_bytes = await save_attachment(sub_id, file)
    content_type = file.content_type or "application/octet-stream"

    async with db.execute(
        """
        INSERT INTO subscription_attachments
            (subscription_id, filename, content_type, size_bytes, storage_path)
        VALUES (?, ?, ?, ?, ?)
        RETURNING id, filename, content_type, size_bytes, uploaded_at
        """,
        (sub_id, filename, content_type, size_bytes, storage_path),
    ) as cur:
        row = await cur.fetchone()
    await db.commit()

    suggested_updates = await analyze_attachment_for_updates(
        db,
        storage_path=storage_path,
        filename=filename,
        content_type=content_type,
        existing_fields={
            "name": existing["name"],
            "provider_name": existing.get("provider_name"),
            "recurring_interval": existing["recurring_interval"],
            "recurring_date": existing.get("recurring_date"),
            "end_date": existing.get("end_date"),
            "amount": existing["amount"],
            "currency": existing["currency"],
            "category_name": existing.get("category_name"),
        },
        kind="subscription",
    )

    return AttachmentUploadResult(
        attachment=AttachmentResponse(**dict(row)),
        suggested_updates=suggested_updates,
    )


@router.get(
    "/api/buckets/{bucket_id}/subscriptions/{sub_id}/attachments/{attachment_id}",
)
async def download_attachment(
    bucket_id: str,
    sub_id: str,
    attachment_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> FileResponse:
    await _check_bucket_access(bucket_id, user, db)
    await _get_sub_or_404(bucket_id, sub_id, db)
    attachment = await _get_attachment_or_404(sub_id, attachment_id, db)

    file_path = attachments_dir() / attachment["storage_path"]
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Attachment file missing on disk")

    return FileResponse(
        path=str(file_path),
        media_type=attachment["content_type"],
        filename=attachment["filename"],
    )


@router.delete(
    "/api/buckets/{bucket_id}/subscriptions/{sub_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_attachment(
    bucket_id: str,
    sub_id: str,
    attachment_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> None:
    await _check_bucket_access(bucket_id, user, db)
    await _get_sub_or_404(bucket_id, sub_id, db)
    attachment = await _get_attachment_or_404(sub_id, attachment_id, db)

    await db.execute(
        "DELETE FROM subscription_attachments WHERE id = ?", (attachment_id,)
    )
    await db.commit()

    delete_attachment_file(attachment["storage_path"])


@router.get(
    "/api/buckets/{bucket_id}/subscriptions/{sub_id}/history",
    response_model=list[HistoryEntryResponse],
)
async def get_subscription_history(
    bucket_id: str,
    sub_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[dict]:
    await _check_bucket_access(bucket_id, user, db)
    await _get_sub_or_404(bucket_id, sub_id, db)
    return await get_history(
        db, table="subscription_history", id_column="subscription_id", entity_id=sub_id
    )

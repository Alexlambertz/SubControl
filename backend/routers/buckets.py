"""
Buckets router — CRUD for buckets and user-bucket membership.

Routes
------
GET    /api/buckets                         List buckets (current user's)
POST   /api/buckets                         Create bucket
GET    /api/buckets/{bucket_id}             Get single bucket
PUT    /api/buckets/{bucket_id}             Rename bucket
DELETE /api/buckets/{bucket_id}             Delete bucket (admin only)
POST   /api/buckets/{bucket_id}/users/{uid} Assign user to bucket (admin)
DELETE /api/buckets/{bucket_id}/users/{uid} Remove user from bucket (admin)
"""

from __future__ import annotations

import logging

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

from backend.database import get_db
from backend.dependencies import CurrentUser, get_current_user, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/buckets", tags=["buckets"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BucketCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Bucket name must not be empty")
        return v.strip()


class BucketUpdate(BucketCreate):
    pass


class BucketResponse(BaseModel):
    id: str
    name: str
    created_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_bucket_or_404(bucket_id: str, db: aiosqlite.Connection) -> dict:
    async with db.execute(
        "SELECT id, name, created_at FROM buckets WHERE id = ?", (bucket_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Bucket not found")
    return dict(row)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[BucketResponse])
async def list_buckets(
    _user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[BucketResponse]:
    """Return all buckets (admin sees all; regular users see their assigned buckets)."""
    async with db.execute(
        "SELECT id, name, created_at FROM buckets ORDER BY name"
    ) as cur:
        rows = await cur.fetchall()
    return [BucketResponse(**dict(r)) for r in rows]


@router.post("", response_model=BucketResponse, status_code=status.HTTP_201_CREATED)
async def create_bucket(
    body: BucketCreate,
    _user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> BucketResponse:
    """Create a new bucket.  Returns 409 if the name already exists."""
    try:
        async with db.execute(
            "INSERT INTO buckets (name) VALUES (?) RETURNING id, name, created_at",
            (body.name,),
        ) as cur:
            row = await cur.fetchone()
        await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A bucket named '{body.name}' already exists",
        )
    return BucketResponse(**dict(row))


@router.get("/{bucket_id}", response_model=BucketResponse)
async def get_bucket(
    bucket_id: str,
    _user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> BucketResponse:
    return BucketResponse(**await _get_bucket_or_404(bucket_id, db))


@router.put("/{bucket_id}", response_model=BucketResponse)
async def update_bucket(
    bucket_id: str,
    body: BucketUpdate,
    _user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> BucketResponse:
    """Rename a bucket."""
    await _get_bucket_or_404(bucket_id, db)
    try:
        await db.execute(
            "UPDATE buckets SET name = ? WHERE id = ?", (body.name, bucket_id)
        )
        await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A bucket named '{body.name}' already exists",
        )
    return BucketResponse(**await _get_bucket_or_404(bucket_id, db))


@router.delete("/{bucket_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_bucket(
    bucket_id: str,
    _user: CurrentUser = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> None:
    """Delete a bucket and all its subscriptions (cascade).  Admin only."""
    await _get_bucket_or_404(bucket_id, db)
    await db.execute("DELETE FROM buckets WHERE id = ?", (bucket_id,))
    await db.commit()


# ---------------------------------------------------------------------------
# User ↔ Bucket membership
# ---------------------------------------------------------------------------


@router.post("/{bucket_id}/users/{user_id}", status_code=status.HTTP_200_OK)
async def assign_user_to_bucket(
    bucket_id: str,
    user_id: str,
    _admin: CurrentUser = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """Assign a user to a bucket.  Admin only."""
    await _get_bucket_or_404(bucket_id, db)

    async with db.execute("SELECT id FROM users WHERE id = ?", (user_id,)) as cur:
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="User not found")

    await db.execute(
        "INSERT OR IGNORE INTO user_buckets (user_id, bucket_id) VALUES (?, ?)",
        (user_id, bucket_id),
    )
    await db.commit()
    return {"user_id": user_id, "bucket_id": bucket_id}


@router.delete("/{bucket_id}/users/{user_id}", status_code=status.HTTP_200_OK)
async def remove_user_from_bucket(
    bucket_id: str,
    user_id: str,
    _admin: CurrentUser = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """Remove a user from a bucket.  Admin only."""
    await _get_bucket_or_404(bucket_id, db)
    await db.execute(
        "DELETE FROM user_buckets WHERE user_id = ? AND bucket_id = ?",
        (user_id, bucket_id),
    )
    await db.commit()
    return {"user_id": user_id, "bucket_id": bucket_id}

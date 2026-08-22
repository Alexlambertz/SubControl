"""
Owners router — bucket-scoped master data (a person's name), assignable to
subscriptions and insurances within that bucket.

Unlike providers/categories (one global list shared across all buckets),
each bucket has its own owner list.

Routes
------
GET  /api/buckets/{bucket_id}/owners   List a bucket's owners
POST /api/buckets/{bucket_id}/owners   Create an owner in a bucket
"""

from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator

from backend.database import get_db
from backend.dependencies import CurrentUser, get_current_user
from backend.routers.subscriptions import _check_bucket_access, _get_bucket_or_404

router = APIRouter(prefix="/api/buckets/{bucket_id}/owners", tags=["owners"])


class OwnerCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be empty")
        return v.strip()


class OwnerResponse(BaseModel):
    id: int
    name: str


@router.get("", response_model=list[OwnerResponse])
async def list_owners(
    bucket_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[OwnerResponse]:
    await _get_bucket_or_404(bucket_id, db)
    await _check_bucket_access(bucket_id, user, db)
    async with db.execute(
        "SELECT id, name FROM owners WHERE bucket_id = ? ORDER BY name",
        (bucket_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [OwnerResponse(**dict(r)) for r in rows]


@router.post("", response_model=OwnerResponse, status_code=status.HTTP_201_CREATED)
async def create_owner(
    bucket_id: str,
    body: OwnerCreate,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> OwnerResponse:
    await _get_bucket_or_404(bucket_id, db)
    await _check_bucket_access(bucket_id, user, db)
    try:
        async with db.execute(
            "INSERT INTO owners (bucket_id, name) VALUES (?, ?) RETURNING id, name",
            (bucket_id, body.name),
        ) as cur:
            row = await cur.fetchone()
        await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Owner '{body.name}' already exists in this bucket",
        )
    return OwnerResponse(**dict(row))

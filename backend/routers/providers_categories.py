"""
Providers and Categories routers.

Routes
------
GET  /api/providers          List all providers
POST /api/providers          Create a provider
GET  /api/categories         List all categories
POST /api/categories         Create a category
"""

from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.database import get_db
from backend.dependencies import CurrentUser, get_current_user

providers_router = APIRouter(prefix="/api/providers", tags=["providers"])
categories_router = APIRouter(prefix="/api/categories", tags=["categories"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ProviderCreate(BaseModel):
    name: str


class ProviderResponse(BaseModel):
    id: int
    name: str


class CategoryCreate(BaseModel):
    name: str


class CategoryResponse(BaseModel):
    id: int
    name: str


# ---------------------------------------------------------------------------
# Provider routes
# ---------------------------------------------------------------------------


@providers_router.get("", response_model=list[ProviderResponse])
async def list_providers(
    _user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[ProviderResponse]:
    async with db.execute("SELECT id, name FROM providers ORDER BY name") as cur:
        rows = await cur.fetchall()
    return [ProviderResponse(**dict(r)) for r in rows]


@providers_router.post(
    "", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED
)
async def create_provider(
    body: ProviderCreate,
    _user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> ProviderResponse:
    try:
        async with db.execute(
            "INSERT INTO providers (name) VALUES (?) RETURNING id, name", (body.name,)
        ) as cur:
            row = await cur.fetchone()
        await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Provider '{body.name}' already exists",
        )
    return ProviderResponse(**dict(row))


# ---------------------------------------------------------------------------
# Category routes
# ---------------------------------------------------------------------------


@categories_router.get("", response_model=list[CategoryResponse])
async def list_categories(
    _user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[CategoryResponse]:
    async with db.execute("SELECT id, name FROM categories ORDER BY name") as cur:
        rows = await cur.fetchall()
    return [CategoryResponse(**dict(r)) for r in rows]


@categories_router.post(
    "", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED
)
async def create_category(
    body: CategoryCreate,
    _user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> CategoryResponse:
    try:
        async with db.execute(
            "INSERT INTO categories (name) VALUES (?) RETURNING id, name",
            (body.name,),
        ) as cur:
            row = await cur.fetchone()
        await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Category '{body.name}' already exists",
        )
    return CategoryResponse(**dict(row))

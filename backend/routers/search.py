"""
Global search endpoint.

GET /api/search?q=<query>
    Full-text search across buckets and subscriptions.
    Returns results grouped by type, ordered alphabetically within each group.
"""

from __future__ import annotations

import logging

import aiosqlite
from fastapi import APIRouter, Depends, Query

from backend.database import get_db
from backend.dependencies import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    limit: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """
    Search across buckets and subscriptions the current user has access to.

    Matches are case-insensitive substring matches on:
    - Bucket name
    - Subscription name, provider name, or category name

    Returns a dict with ``query`` and ``results`` (list of typed result objects).
    """
    pattern = f"%{q}%"
    results: list[dict] = []

    # ── Buckets — only those the user can access ──────────────────────────────
    if user.is_admin:
        bucket_query = (
            "SELECT id, name FROM buckets WHERE name LIKE ? COLLATE NOCASE ORDER BY name LIMIT ?",
            (pattern, limit),
        )
    else:
        bucket_query = (
            """
            SELECT b.id, b.name
            FROM   buckets b
            JOIN   user_buckets ub ON ub.bucket_id = b.id
            WHERE  ub.user_id = ?
              AND  b.name LIKE ? COLLATE NOCASE
            ORDER  BY b.name
            LIMIT  ?
            """,
            (user.id, pattern, limit),
        )

    async with db.execute(*bucket_query) as cur:
        for row in await cur.fetchall():
            results.append(
                {
                    "type": "bucket",
                    "id": row["id"],
                    "name": row["name"],
                }
            )

    # ── Subscriptions — only from accessible buckets ──────────────────────────
    if user.is_admin:
        sub_access = ""
        sub_params: tuple = (pattern, pattern, pattern, limit)
    else:
        sub_access = "AND s.bucket_id IN (SELECT bucket_id FROM user_buckets WHERE user_id = ?)"
        sub_params = (pattern, pattern, pattern, user.id, limit)

    async with db.execute(
        f"""
        SELECT s.id,
               s.name,
               s.amount,
               s.currency,
               s.recurring_interval,
               s.bucket_id,
               s.image_url,
               b.name  AS bucket_name,
               p.name  AS provider_name,
               c.name  AS category_name
        FROM   subscriptions s
        LEFT   JOIN buckets    b ON s.bucket_id   = b.id
        LEFT   JOIN providers  p ON s.provider_id = p.id
        LEFT   JOIN categories c ON s.category_id = c.id
        WHERE  (  s.name LIKE ?  COLLATE NOCASE
               OR p.name LIKE ?  COLLATE NOCASE
               OR c.name LIKE ?  COLLATE NOCASE
               )
        {sub_access}
        ORDER  BY s.name
        LIMIT  ?
        """,
        sub_params,
    ) as cur:
        for row in await cur.fetchall():
            results.append(
                {
                    "type": "subscription",
                    "id": row["id"],
                    "name": row["name"],
                    "amount": row["amount"],
                    "currency": row["currency"],
                    "recurring_interval": row["recurring_interval"],
                    "bucket_id": row["bucket_id"],
                    "bucket_name": row["bucket_name"],
                    "provider_name": row["provider_name"],
                    "category_name": row["category_name"],
                    "image_url": row["image_url"],
                }
            )

    logger.info("Search q=%r → %d results", q, len(results))
    return {"query": q, "results": results}

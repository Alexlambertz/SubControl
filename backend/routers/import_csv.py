"""
CSV import / export router.

Routes
------
POST /api/buckets/{bucket_id}/subscriptions/import
    Upload a CSV file to bulk-import subscriptions into a bucket.

GET /api/buckets/{bucket_id}/subscriptions/export
    Download all subscriptions in a bucket as a CSV file.
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from backend.database import get_db, get_db_path
from backend.dependencies import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["subscriptions"])

# Columns written to the exported CSV (matches the import format)
_EXPORT_COLUMNS = [
    "name", "provider", "recurring_interval", "recurring_date",
    "end_date", "amount", "currency", "category",
]


@router.post("/api/buckets/{bucket_id}/subscriptions/import")
async def import_subscriptions(
    bucket_id: str,
    file: UploadFile,
    _user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """
    Bulk-import subscriptions from a CSV file into *bucket_id*.

    Returns per-row success/error information.
    """
    async with db.execute("SELECT id FROM buckets WHERE id = ?", (bucket_id,)) as cur:
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Bucket not found")

    content = await file.read()

    from backend.services.csv_import import import_subscriptions_from_csv

    result = await import_subscriptions_from_csv(content, bucket_id, db)

    logger.info(
        "CSV import for bucket %s: %d imported, %d failed",
        bucket_id,
        result["imported"],
        len(result["failed"]),
    )

    # Kick off logo fetching in the background for newly imported subscriptions
    if result["imported"] > 0:
        from backend.services.logo_fetch import refresh_logos_for_bucket
        asyncio.create_task(
            refresh_logos_for_bucket(bucket_id, get_db_path(), only_missing=True)
        )

    return result


@router.post("/api/buckets/{bucket_id}/subscriptions/refresh-logos")
async def refresh_subscription_logos(
    bucket_id: str,
    _user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """
    Re-fetch and store logo URLs for every subscription in *bucket_id*.

    Returns immediately; the actual fetching runs as a background task.
    """
    async with db.execute("SELECT id FROM buckets WHERE id = ?", (bucket_id,)) as cur:
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Bucket not found")

    async with db.execute(
        "SELECT COUNT(*) AS n FROM subscriptions WHERE bucket_id = ?", (bucket_id,)
    ) as cur:
        row = await cur.fetchone()
    subscription_count = row["n"] if row else 0

    from backend.services.logo_fetch import refresh_logos_for_bucket
    asyncio.create_task(
        refresh_logos_for_bucket(bucket_id, get_db_path(), only_missing=False)
    )

    logger.info(
        "Logo refresh started for bucket %s (%d subscriptions)", bucket_id, subscription_count
    )
    return {"status": "started", "subscriptions": subscription_count}


@router.get("/api/buckets/{bucket_id}/subscriptions/export")
async def export_subscriptions(
    bucket_id: str,
    _user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> StreamingResponse:
    """
    Export all subscriptions in *bucket_id* as a CSV download.

    The column layout matches the import format so exported files can be
    re-imported directly.
    """
    async with db.execute("SELECT id, name FROM buckets WHERE id = ?", (bucket_id,)) as cur:
        bucket_row = await cur.fetchone()
    if bucket_row is None:
        raise HTTPException(status_code=404, detail="Bucket not found")

    bucket_name = bucket_row["name"]

    async with db.execute(
        """
        SELECT s.name,
               p.name  AS provider,
               s.recurring_interval,
               s.recurring_date,
               s.end_date,
               s.amount,
               s.currency,
               c.name  AS category
        FROM subscriptions s
        LEFT JOIN providers p  ON s.provider_id  = p.id
        LEFT JOIN categories c ON s.category_id  = c.id
        WHERE s.bucket_id = ?
        ORDER BY s.name
        """,
        (bucket_id,),
    ) as cur:
        rows = await cur.fetchall()

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_EXPORT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: (row[k] or "") for k in _EXPORT_COLUMNS})

    csv_bytes = output.getvalue().encode("utf-8")
    filename = f"{bucket_name.replace(' ', '_')}_subscriptions.csv"

    logger.info("CSV export for bucket %s: %d rows", bucket_id, len(rows))

    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

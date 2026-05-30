"""
External-source import router.

Routes
------
POST /api/import/wallos
    Import subscriptions from a Wallos instance into a chosen bucket.

More importers can be added here as additional POST endpoints under /api/import/*.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from backend.database import get_db
from backend.dependencies import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/import", tags=["import"])


# ---------------------------------------------------------------------------
# Wallos
# ---------------------------------------------------------------------------


class WallosImportRequest(BaseModel):
    url: str
    api_key: str
    bucket_id: str
    skip_inactive: bool = True

    @field_validator("url")
    @classmethod
    def url_not_empty(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v:
            raise ValueError("url must not be empty")
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        # SSRF guard — block private/loopback/link-local addresses
        parsed = urlparse(v)
        hostname = parsed.hostname or ""
        try:
            addr = ipaddress.ip_address(hostname)
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                raise ValueError("Private or internal IP addresses are not allowed")
        except ValueError as exc:
            # Not an IP literal — resolve hostname to check
            if "not allowed" in str(exc):
                raise
            try:
                ip_str = socket.gethostbyname(hostname)
                addr = ipaddress.ip_address(ip_str)
                if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                    raise ValueError("URL resolves to a private or internal address")
            except socket.gaierror:
                pass  # DNS will fail later; let httpx handle it
        return v

    @field_validator("api_key")
    @classmethod
    def key_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("api_key must not be empty")
        return v.strip()


class ImportResult(BaseModel):
    imported: int
    skipped: int
    failed: list[dict]


@router.post("/wallos", response_model=ImportResult)
async def import_from_wallos(
    body: WallosImportRequest,
    _user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> ImportResult:
    """
    Fetch all subscriptions from a Wallos instance and store them in *bucket_id*.

    Inactive subscriptions are skipped by default (pass ``skip_inactive: false``
    to include them).
    """
    # Verify bucket exists
    async with db.execute(
        "SELECT id FROM buckets WHERE id = ?", (body.bucket_id,)
    ) as cur:
        if await cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Bucket not found")

    # Enforce bucket membership for non-admins
    if not _user.is_admin:
        async with db.execute(
            "SELECT 1 FROM user_buckets WHERE user_id = ? AND bucket_id = ?",
            (_user.id, body.bucket_id),
        ) as cur:
            if await cur.fetchone() is None:
                raise HTTPException(status_code=403, detail="Access denied to this bucket")

    from backend.services.wallos_import import import_from_wallos

    try:
        result = await import_from_wallos(
            base_url=body.url,
            api_key=body.api_key,
            bucket_id=body.bucket_id,
            db=db,
            skip_inactive=body.skip_inactive,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info(
        "Wallos import for bucket %s: %d imported, %d skipped, %d failed",
        body.bucket_id,
        result["imported"],
        result["skipped"],
        len(result["failed"]),
    )

    # Fire logo fetches for all successfully imported subscriptions
    import asyncio
    from backend.database import get_db_path
    from backend.services.logo_fetch import fetch_logo_url

    db_path = get_db_path()

    async def _fetch_logos() -> None:
        async with aiosqlite.connect(db_path) as logo_db:
            async with logo_db.execute(
                "SELECT id, name FROM subscriptions WHERE bucket_id = ? ORDER BY created_at DESC LIMIT ?",
                (body.bucket_id, result["imported"]),
            ) as cur:
                rows = await cur.fetchall()
        for sub_id, sub_name in rows:
            url = await fetch_logo_url(sub_name)
            if url:
                async with aiosqlite.connect(db_path) as logo_db:
                    await logo_db.execute(
                        "UPDATE subscriptions SET image_url = ? WHERE id = ?",
                        (url, sub_id),
                    )
                    await logo_db.commit()

    if result["imported"] > 0:
        asyncio.create_task(_fetch_logos())

    return ImportResult(**result)

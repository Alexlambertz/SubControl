"""
Logo/image auto-fetch service.

Strategy
--------
1. Derive a domain name from the provider name (e.g. "Netflix" → "netflix.com").
2. Try the Clearbit Logo API: ``https://logo.clearbit.com/{domain}``
   - HTTP 200 → return that URL.
   - Any other response or connection error → fallback.
3. Fallback: return the Google Favicon service URL
   ``https://www.google.com/s2/favicons?domain={domain}&sz=128``
   (no live HTTP call needed — the browser will fetch it directly).
4. If the domain cannot be determined → return None.

The returned URL is stored in ``subscriptions.image_url``.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    pass  # aiosqlite imported lazily inside refresh_logos_for_bucket

logger = logging.getLogger(__name__)

_CLEARBIT_BASE = "https://logo.clearbit.com"
_GOOGLE_FAVICON_BASE = "https://www.google.com/s2/favicons"

# Characters that are not valid in a simple hostname
_NON_ALPHA = re.compile(r"[^a-z0-9-]")


def _derive_domain(provider_name: str) -> str | None:
    """
    Convert a provider display name to a best-guess domain.

    Examples
    --------
    "Netflix"     → "netflix.com"
    "Amazon Prime"→ "amazon.com"   (first word only)
    "HBO Max"     → "hbo.com"
    ""            → None
    """
    if not provider_name or not provider_name.strip():
        return None

    # Take the first word, lowercase, strip non-alphanumeric
    first_word = provider_name.strip().split()[0].lower()
    cleaned = _NON_ALPHA.sub("", first_word)
    if not cleaned:
        return None
    return f"{cleaned}.com"


async def fetch_logo_url(provider_name: str) -> str | None:
    """
    Fetch a logo URL for the given provider name.

    Returns the URL string on success, or None if no logo could be found.
    This function never raises; errors are logged and None is returned.
    """
    domain = _derive_domain(provider_name)
    if domain is None:
        return None

    clearbit_url = f"{_CLEARBIT_BASE}/{domain}"
    google_url = f"{_GOOGLE_FAVICON_BASE}?domain={domain}&sz=128"

    # --- Try Clearbit ---
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(clearbit_url)
            if resp.status_code == 200:
                logger.debug("Logo found via Clearbit for %r: %s", provider_name, clearbit_url)
                return clearbit_url
    except httpx.HTTPError as exc:
        logger.debug("Clearbit request failed for %r: %s", provider_name, exc)

    # --- Fall back to Google Favicon ---
    # We return the URL without verifying it; the browser will handle missing icons.
    logger.debug("Falling back to Google Favicon for %r: %s", provider_name, google_url)
    return google_url


async def refresh_logos_for_bucket(
    bucket_id: str,
    db_path: str,
    *,
    only_missing: bool = False,
) -> None:
    """
    Fetch and store logo URLs for every subscription in *bucket_id*.

    Safe to run as an ``asyncio.create_task`` background job — opens its own
    DB connections and never raises (errors are logged).

    Parameters
    ----------
    bucket_id:
        Target bucket.
    db_path:
        Filesystem path to the SQLite database.
    only_missing:
        When True, skip subscriptions that already have an ``image_url``.
        Use this for post-import runs where existing logos should be kept.
        When False (default), re-fetch logos for all subscriptions.
    """
    import aiosqlite

    where_extra = " AND s.image_url IS NULL" if only_missing else ""
    query = f"""
        SELECT s.id, COALESCE(p.name, s.name) AS provider_name
        FROM subscriptions s
        LEFT JOIN providers p ON s.provider_id = p.id
        WHERE s.bucket_id = ?{where_extra}
    """

    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (bucket_id,)) as cur:
                rows = list(await cur.fetchall())
    except Exception:
        logger.exception("refresh_logos_for_bucket: failed to query subscriptions")
        return

    logger.info(
        "refresh_logos_for_bucket: refreshing %d logo(s) for bucket %s (only_missing=%s)",
        len(rows),
        bucket_id,
        only_missing,
    )

    for row in rows:
        url = await fetch_logo_url(row["provider_name"])
        if url is None:
            continue
        try:
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "UPDATE subscriptions SET image_url = ? WHERE id = ?",
                    (url, row["id"]),
                )
                await db.commit()
        except Exception:
            logger.exception(
                "refresh_logos_for_bucket: failed to update image_url for sub %s",
                row["id"],
            )

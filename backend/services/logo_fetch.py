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

The returned URL is stored in ``subscriptions.image_url``. Results are cached
in-process per provider name (see ``_LOGO_CACHE``) so the same provider
(e.g. "Netflix" across many buckets) is never fetched from Clearbit twice.
"""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

logger = logging.getLogger(__name__)

_CLEARBIT_BASE = "https://logo.clearbit.com"
_GOOGLE_FAVICON_BASE = "https://www.google.com/s2/favicons"

# Characters that are not valid in a simple hostname
_NON_ALPHA = re.compile(r"[^a-z0-9-]")

# Process-lifetime cache: provider name -> resolved logo URL (or None).
# Provider logos essentially never change, so no TTL/eviction is needed.
_LOGO_CACHE: dict[str, str | None] = {}

# Bound concurrent outbound HTTP calls when refreshing many logos at once.
_MAX_CONCURRENT_FETCHES = 8


def clear_logo_cache() -> None:
    """Reset the in-process logo cache. Mainly for test isolation."""
    _LOGO_CACHE.clear()


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


async def fetch_logo_url(
    provider_name: str, *, client: httpx.AsyncClient | None = None
) -> str | None:
    """
    Fetch a logo URL for the given provider name.

    Returns the URL string on success, or None if no logo could be found.
    This function never raises; errors are logged and None is returned.

    Checks the in-process cache first. Pass an existing *client* to reuse a
    connection pool when fetching many logos in a batch (a fresh short-lived
    client is created otherwise, preserving single-call-site behaviour).
    """
    domain = _derive_domain(provider_name)
    if domain is None:
        return None

    if provider_name in _LOGO_CACHE:
        return _LOGO_CACHE[provider_name]

    clearbit_url = f"{_CLEARBIT_BASE}/{domain}"
    google_url = f"{_GOOGLE_FAVICON_BASE}?domain={domain}&sz=128"

    async def _resolve() -> str:
        # --- Try Clearbit ---
        try:
            if client is not None:
                resp = await client.get(clearbit_url)
            else:
                async with httpx.AsyncClient(timeout=5) as one_off:
                    resp = await one_off.get(clearbit_url)
            if resp.status_code == 200:
                logger.debug("Logo found via Clearbit for %r: %s", provider_name, clearbit_url)
                return clearbit_url
        except httpx.HTTPError as exc:
            logger.debug("Clearbit request failed for %r: %s", provider_name, exc)

        # --- Fall back to Google Favicon ---
        # We return the URL without verifying it; the browser will handle missing icons.
        logger.debug("Falling back to Google Favicon for %r: %s", provider_name, google_url)
        return google_url

    url = await _resolve()
    _LOGO_CACHE[provider_name] = url
    return url


async def refresh_logos_for_bucket(
    bucket_id: str,
    db_path: str,
    *,
    only_missing: bool = False,
) -> None:
    """
    Fetch and store logo URLs for every subscription in *bucket_id*.

    Safe to run as an ``asyncio.create_task`` background job — opens its own
    DB connection and never raises (errors are logged). Fetches are done
    concurrently (bounded by a semaphore) over one shared HTTP client, and
    all resulting updates are written in a single ``executemany`` on one DB
    connection, instead of one connection + commit per subscription.

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

    if not rows:
        return

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_FETCHES)
    results: dict[str, str] = {}

    async def _fetch_one(row, client: httpx.AsyncClient) -> None:
        async with semaphore:
            url = await fetch_logo_url(row["provider_name"], client=client)
            if url is not None:
                results[row["id"]] = url

    async with httpx.AsyncClient(timeout=5) as client:
        await asyncio.gather(*(_fetch_one(row, client) for row in rows))

    if not results:
        return

    try:
        async with aiosqlite.connect(db_path) as db:
            await db.executemany(
                "UPDATE subscriptions SET image_url = ? WHERE id = ?",
                [(url, sub_id) for sub_id, url in results.items()],
            )
            await db.commit()
    except Exception:
        logger.exception(
            "refresh_logos_for_bucket: failed to write %d logo update(s)", len(results)
        )

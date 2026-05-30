"""
WallOS / Wallos import service.

Fetches subscriptions from a self-hosted Wallos instance via its REST API
and converts them into SubControl subscriptions.

Wallos API
----------
GET  {base_url}/api/subscriptions?token={api_key}

Response shape (fields that matter):
    {
      "success": true,
      "subscriptions": [
        {
          "name": "Netflix",
          "price": 12.99,
          "currency_id": "EUR",
          "payment_cycle": "monthly",
          "next_payment_date": "2025-06-15",   // may be absent / null
          "category_name": "Entertainment",     // or "category": {"name": "..."}
          "inactive": 0,
          "logo": "netflix.png"                 // logo filename, not a full URL
        }
      ]
    }

Interval mapping (Wallos → SubControl)
---------------------------------------
monthly     → monthly
yearly      → yearly
weekly      → weekly
daily       → daily
quarterly   → quarterly
half-yearly → half-year
biannually  → half-year      (alternative Wallos label)
every2weeks → weekly         (approximate — not ideal, but avoids rejection)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import aiosqlite
import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Interval normalisation
# ---------------------------------------------------------------------------

_INTERVAL_MAP: dict[str, str] = {
    "daily": "daily",
    "weekly": "weekly",
    "monthly": "monthly",
    "quarterly": "quarterly",
    "half-yearly": "half-year",
    "halfyearly": "half-year",
    "half_yearly": "half-year",
    "biannually": "half-year",
    "semi-annually": "half-year",
    "yearly": "yearly",
    "annually": "yearly",
    "annual": "yearly",
}

VALID_INTERVALS = {"daily", "weekly", "monthly", "quarterly", "half-year", "yearly"}


def _normalise_interval(raw: str | None) -> str | None:
    """Map a Wallos payment_cycle string to a SubControl interval, or None."""
    if not raw:
        return None
    return _INTERVAL_MAP.get(raw.lower().strip())


# ---------------------------------------------------------------------------
# DB helpers (shared pattern with csv_import)
# ---------------------------------------------------------------------------


async def _get_or_create_provider(name: str, db: aiosqlite.Connection) -> int:
    async with db.execute("SELECT id FROM providers WHERE name = ?", (name,)) as cur:
        row = await cur.fetchone()
    if row:
        return row["id"]
    async with db.execute(
        "INSERT INTO providers (name) VALUES (?) RETURNING id", (name,)
    ) as cur:
        row = await cur.fetchone()
    return row["id"]


async def _get_or_create_category(
    name: str | None, db: aiosqlite.Connection
) -> Optional[int]:
    if not name or not name.strip():
        return None
    name = name.strip()
    async with db.execute("SELECT id FROM categories WHERE name = ?", (name,)) as cur:
        row = await cur.fetchone()
    if row:
        return row["id"]
    async with db.execute(
        "INSERT INTO categories (name) VALUES (?) RETURNING id", (name,)
    ) as cur:
        row = await cur.fetchone()
    return row["id"]


# ---------------------------------------------------------------------------
# Wallos response parsing
# ---------------------------------------------------------------------------


def _parse_subscription(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Extract the relevant fields from a single Wallos subscription dict.

    Returns a normalised dict ready for insertion.
    Raises ValueError with a human-readable message for unusable rows.
    """
    name = (raw.get("name") or "").strip()
    if not name:
        raise ValueError("subscription has no name")

    # Price
    price = raw.get("price")
    try:
        amount = float(price)
    except (TypeError, ValueError):
        raise ValueError(f"cannot parse price '{price}' as a number")

    # Currency — Wallos uses "currency_id" (ISO code) or sometimes "currency"
    currency = (
        raw.get("currency_id") or raw.get("currency") or "EUR"
    ).strip().upper()

    # Interval
    raw_cycle = raw.get("payment_cycle") or raw.get("cycle") or ""
    interval = _normalise_interval(raw_cycle)
    if not interval:
        raise ValueError(
            f"unsupported payment_cycle '{raw_cycle}'; "
            f"expected one of {sorted(_INTERVAL_MAP)}"
        )

    # Category — Wallos may supply category_name directly or as a nested dict
    category_name: str | None = None
    if "category_name" in raw and raw["category_name"]:
        category_name = str(raw["category_name"]).strip() or None
    elif isinstance(raw.get("category"), dict):
        category_name = (raw["category"].get("name") or "").strip() or None

    # Last payment date — recurring_date stores the LAST payment, not the next.
    # Wallos may provide last_payment_date directly; if only next_payment_date
    # is available we subtract one interval to recover the last-payment date.
    recurring_date: str | None = None
    for key in ("last_payment_date", "payment_date_iso"):
        val = raw.get(key)
        if val and isinstance(val, str) and len(val) >= 10:
            recurring_date = val[:10]  # keep YYYY-MM-DD only
            break

    if not recurring_date:
        next_val = raw.get("next_payment_date")
        if next_val and isinstance(next_val, str) and len(next_val) >= 10:
            from datetime import date as _date
            from backend.services.dashboard import _INTERVAL_DELTAS
            next_date = _date.fromisoformat(next_val[:10])
            delta = _INTERVAL_DELTAS.get(interval, None)
            if delta is not None:
                recurring_date = (next_date - delta).isoformat()

    return {
        "name": name,
        "provider_name": name,  # use subscription name as provider fallback
        "amount": amount,
        "currency": currency,
        "recurring_interval": interval,
        "recurring_date": recurring_date,
        "category_name": category_name,
        "inactive": bool(raw.get("inactive", 0)),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def import_from_wallos(
    base_url: str,
    api_key: str,
    bucket_id: str,
    db: aiosqlite.Connection,
    *,
    skip_inactive: bool = True,
    timeout: float = 15.0,
) -> dict:
    """
    Fetch subscriptions from a Wallos instance and import them into *bucket_id*.

    Parameters
    ----------
    base_url:
        Root URL of the Wallos instance, e.g. ``"https://wallos.example.com"``.
        Trailing slashes are stripped automatically.
    api_key:
        Wallos API token.
    bucket_id:
        Target SubControl bucket (caller must verify it exists).
    db:
        Open aiosqlite connection.
    skip_inactive:
        If True (default), subscriptions with ``inactive=1`` are ignored.
    timeout:
        HTTP request timeout in seconds.

    Returns
    -------
    ``{"imported": int, "skipped": int, "failed": [{"name": str, "error": str}]}``
    """
    base_url = base_url.rstrip("/")
    url = f"{base_url}/api/subscriptions"

    logger.info("Fetching subscriptions from Wallos: %s", url)

    # Wallos expects the key as 'api_key' (also accepts 'apiKey') via $_REQUEST,
    # so it works with both GET query-param and POST form body.
    # We send it as a query parameter (GET) and also in the Authorization header
    # so the request survives nginx setups that strip query strings.
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        # A neutral User-Agent avoids nginx bot-filtering rules.
        "User-Agent": "SubControl/1.0",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(
                url,
                params={"api_key": api_key},
                headers=headers,
            )
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        body = exc.response.text[:300].strip()
        if status == 403:
            raise ValueError(
                "Wallos returned 403 Forbidden.\n\n"
                "The API path (/api/subscriptions) is blocked by the nginx reverse proxy "
                "before the request reaches Wallos itself. To fix this, add an allow rule "
                "to your nginx configuration for the /api/ location:\n\n"
                "    location /api/ {\n"
                "        allow all;   # or restrict to specific IPs\n"
                "        ...\n"
                "    }\n\n"
                "Other possible causes:\n"
                "• The Wallos URL points to a sub-path instead of the app root "
                "(e.g. use https://wallos.example.com, not https://example.com/wallos).\n"
                "• Basic-auth or IP-allowlist is configured on the nginx vhost."
            ) from exc
        if status == 401:
            raise ValueError(
                "Wallos returned 401 Unauthorized — the API key is invalid. "
                "Copy it from Wallos → Settings → API."
            ) from exc
        raise ValueError(
            f"Wallos API returned HTTP {status}: {body}"
        ) from exc
    except httpx.RequestError as exc:
        raise ValueError(f"Could not reach Wallos instance: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Unexpected error contacting Wallos: {exc}") from exc

    if not payload.get("success"):
        raise ValueError(
            f"Wallos API reported failure: {payload.get('error') or payload}"
        )

    raw_subs: list[dict] = payload.get("subscriptions") or payload.get("data") or []
    if not isinstance(raw_subs, list):
        raise ValueError("Wallos API response did not contain a subscription list")

    logger.info("Wallos returned %d subscription(s)", len(raw_subs))

    imported = 0
    skipped = 0
    failed: list[dict] = []

    for raw in raw_subs:
        try:
            sub = _parse_subscription(raw)
        except ValueError as exc:
            name = (raw.get("name") or "").strip() or "<unknown>"
            logger.debug("Wallos subscription '%s' parse error: %s", name, exc)
            failed.append({"name": name, "error": str(exc)})
            continue

        if skip_inactive and sub["inactive"]:
            skipped += 1
            continue

        try:
            provider_id = await _get_or_create_provider(sub["provider_name"], db)
            category_id = await _get_or_create_category(sub["category_name"], db)

            await db.execute(
                """
                INSERT INTO subscriptions
                    (bucket_id, name, provider_id, recurring_interval,
                     recurring_date, amount, currency, category_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bucket_id,
                    sub["name"],
                    provider_id,
                    sub["recurring_interval"],
                    sub["recurring_date"],
                    sub["amount"],
                    sub["currency"],
                    category_id,
                ),
            )
            imported += 1
        except Exception as exc:
            logger.exception("DB insert failed for '%s'", sub["name"])
            failed.append({"name": sub["name"], "error": f"Database error: {exc}"})

    await db.commit()
    logger.info(
        "Wallos import complete: %d imported, %d skipped, %d failed",
        imported, skipped, len(failed),
    )
    return {"imported": imported, "skipped": skipped, "failed": failed}

"""
CSV import service for bulk subscription upload.

Expected columns (case-insensitive)
------------------------------------
name               required  — subscription display name
provider           optional* — provider name (created on-the-fly)
recurring_interval optional* — daily|weekly|monthly|quarterly|half-year|yearly
recurring_date     optional  — ISO date (YYYY-MM-DD) of last payment
amount             required  — numeric billing amount
currency           optional  — ISO currency code; defaults to EUR
category           optional  — category name (created on-the-fly)

* These columns are required by default but can be made optional via the
  ``provider_fallback`` / ``default_interval`` parameters described below.

Import options
--------------
provider_fallback : "error" | "use_name" | "skip"
    What to do when a row has no provider value.
    "error"    — mark the row as failed (default, original behaviour).
    "use_name" — use the subscription name as the provider.
    "skip"     — silently skip the row without counting it as a failure.

default_interval : str | None
    Billing interval assumed when a row omits recurring_interval.
    Must be one of the valid interval strings.  ``None`` means the column
    is still required (original behaviour).

default_currency : str
    Currency code used when a row omits the currency column (default "EUR").

Returns
-------
``{"imported": N, "failed": [{"row": N, "error": "..."}]}``

Row numbers in the ``failed`` list are 0-indexed relative to data rows
(not including the header).
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Literal, Optional

import aiosqlite

logger = logging.getLogger(__name__)

VALID_INTERVALS = {"daily", "weekly", "monthly", "quarterly", "half-year", "yearly"}

ProviderFallback = Literal["error", "use_name", "skip"]


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
    name: str, db: aiosqlite.Connection
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


async def import_subscriptions_from_csv(
    file_content: bytes,
    bucket_id: str,
    db: aiosqlite.Connection,
    *,
    provider_fallback: ProviderFallback = "error",
    default_interval: Optional[str] = None,
    default_currency: str = "EUR",
) -> dict:
    """
    Parse *file_content* as CSV and import valid rows as subscriptions.

    Parameters
    ----------
    file_content:
        Raw bytes of the uploaded CSV file.
    bucket_id:
        Target bucket ID (caller must verify it exists first).
    db:
        Open aiosqlite connection.
    provider_fallback:
        Behaviour when a row has no provider — "error" (default), "use_name",
        or "skip".
    default_interval:
        Billing interval to assume when a row omits ``recurring_interval``.
        ``None`` keeps the column required.
    default_currency:
        Currency code to use when a row omits ``currency`` (default "EUR").

    Returns
    -------
    ``{"imported": int, "failed": [{"row": int, "error": str}]}``
    """
    try:
        text = file_content.decode("utf-8-sig")  # strip BOM if present
    except UnicodeDecodeError:
        text = file_content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return {"imported": 0, "failed": []}

    imported = 0
    failed = []

    for row_index, raw_row in enumerate(reader):
        row = {k.strip().lower(): (v.strip() if v else "") for k, v in raw_row.items()}
        try:
            # --- name (always required) ---
            name = row.get("name", "")
            if not name:
                raise ValueError("'name' is required")

            # --- provider (optional depending on fallback) ---
            provider_name = row.get("provider", "")
            if not provider_name:
                if provider_fallback == "use_name":
                    provider_name = name
                    logger.debug(
                        "Row %d: provider missing — using name '%s'", row_index, name
                    )
                elif provider_fallback == "skip":
                    logger.debug("Row %d: provider missing — skipping", row_index)
                    continue
                else:  # "error"
                    raise ValueError(
                        "'provider' is required; "
                        "ask the AI to use 'use_name' fallback if you want to use "
                        "the subscription name instead"
                    )

            # --- recurring_interval ---
            interval = row.get("recurring_interval", "") or default_interval or ""
            if interval not in VALID_INTERVALS:
                if not interval and default_interval is None:
                    raise ValueError(
                        f"'recurring_interval' is required; "
                        f"must be one of {sorted(VALID_INTERVALS)}"
                    )
                raise ValueError(
                    f"invalid recurring_interval '{interval}'; "
                    f"must be one of {sorted(VALID_INTERVALS)}"
                )

            # --- amount (always required) ---
            amount_str = row.get("amount", "")
            if not amount_str:
                raise ValueError("'amount' is required")
            try:
                amount = float(amount_str)
            except ValueError:
                raise ValueError(f"'amount' must be a number, got '{amount_str}'")

            currency = row.get("currency", "") or default_currency
            recurring_date = row.get("recurring_date") or None
            category_name = row.get("category") or None

            # --- Upsert provider / category ---
            provider_id = await _get_or_create_provider(provider_name, db)
            category_id = await _get_or_create_category(category_name or "", db)

            # --- Insert subscription ---
            await db.execute(
                """
                INSERT INTO subscriptions
                    (bucket_id, name, provider_id, recurring_interval,
                     recurring_date, amount, currency, category_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bucket_id,
                    name,
                    provider_id,
                    interval,
                    recurring_date,
                    amount,
                    currency,
                    category_id,
                ),
            )
            imported += 1

        except Exception as exc:
            logger.debug("CSV row %d failed: %s", row_index, exc)
            failed.append({"row": row_index, "error": str(exc)})

    await db.commit()
    return {"imported": imported, "failed": failed}

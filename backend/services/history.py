"""
Per-record change history for subscriptions and insurances.

Records one row per field whose value actually changed on an update — never
on create (there's no "old value" to diff against). Used by
routers/subscriptions.py and routers/insurances.py's update endpoints, which
already resolve a full old-vs-new field set on every call.
"""

from __future__ import annotations

from typing import Any, Optional

import aiosqlite
from pydantic import BaseModel

from backend.dependencies import CurrentUser

# image_url is excluded on purpose — it's auto-fetched by the background
# logo-refresh job, not a user edit, and would spam the log on every refresh.
SUBSCRIPTION_HISTORY_FIELDS = [
    "name", "provider_name", "recurring_interval", "recurring_date",
    "end_date", "amount", "currency", "category_name", "owner_name",
]
INSURANCE_HISTORY_FIELDS = [
    "name", "insurer", "policy_number", "recurring_interval", "recurring_date",
    "end_date", "amount", "currency", "category_name", "notes", "owner_name",
]


class HistoryEntryResponse(BaseModel):
    id: str
    field: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    changed_by_username: str
    changed_at: str


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


async def record_changes(
    db: aiosqlite.Connection,
    *,
    table: str,
    id_column: str,
    entity_id: str,
    old_values: dict[str, Any],
    new_values: dict[str, Any],
    fields: list[str],
    user: CurrentUser,
) -> None:
    """
    Insert one history row per field in *fields* whose value differs between
    *old_values* and *new_values*.

    Does NOT commit — the caller commits once, together with its own
    ``UPDATE``, so the record change and its history entries land in the
    same transaction.
    """
    rows = [
        (
            entity_id,
            field,
            _stringify(old_values.get(field)),
            _stringify(new_values.get(field)),
            user.id,
            user.username,
        )
        for field in fields
        if old_values.get(field) != new_values.get(field)
    ]
    if not rows:
        return
    await db.executemany(
        f"""
        INSERT INTO {table}
            ({id_column}, field, old_value, new_value, changed_by_user_id, changed_by_username)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


async def get_history(
    db: aiosqlite.Connection, *, table: str, id_column: str, entity_id: str
) -> list[dict[str, Any]]:
    """Return up to the 200 most recent history rows for *entity_id*, newest first."""
    async with db.execute(
        f"""
        SELECT id, field, old_value, new_value, changed_by_username, changed_at
        FROM {table}
        WHERE {id_column} = ?
        ORDER BY changed_at DESC
        LIMIT 200
        """,
        (entity_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]

"""
AI Chat service — streams responses from an OpenAI-compatible LLM endpoint.

Architecture
------------
A single streaming API call is made. Chunks are forwarded to the client as
they arrive.  If the model signals ``finish_reason="tool_calls"``, the
accumulated tool call is executed against the DB and a second streaming call
is made that produces the final reply — this too is forwarded chunk by chunk.

Using a single initial call means:
* Text responses reach the user with zero extra latency.
* The redundant "non-streaming probe → streaming repeat" double-call is gone.
* Tool calls are detected reliably from ``finish_reason``, not guessed from
  content text.

DB connections
--------------
The function receives the *database file path* so it can open short-lived
connections independently of the FastAPI request lifecycle.  This avoids the
yield-dependency / StreamingResponse timing bug where the connection is
closed before the generator finishes executing writes.
"""

from __future__ import annotations

import json
import logging
import secrets
from collections.abc import AsyncGenerator
from typing import Any

import aiosqlite

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OpenAI tool schemas
# ---------------------------------------------------------------------------

# Base tools always available in chat
_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create_subscription",
            "description": (
                "Create a new recurring subscription. "
                "Call this whenever the user asks to add, create, or set up a subscription."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bucket_id": {
                        "type": "string",
                        "description": "Exact bucket_id from the bucket list in the system prompt.",
                    },
                    "name": {"type": "string", "description": "Display name of the subscription"},
                    "provider_name": {"type": "string"},
                    "recurring_interval": {
                        "type": "string",
                        "enum": ["daily", "weekly", "monthly", "quarterly", "half-year", "yearly"],
                    },
                    "recurring_date": {
                        "type": "string",
                        "description": "Last payment date, ISO format YYYY-MM-DD. Omit if unknown.",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Optional end date YYYY-MM-DD when billing stops. Omit if ongoing.",
                    },
                    "amount": {"type": "number", "description": "Price per interval"},
                    "currency": {"type": "string", "default": "EUR"},
                    "category_name": {"type": "string"},
                },
                "required": ["bucket_id", "name", "recurring_interval", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_subscription",
            "description": (
                "Update one or more fields of an existing subscription. "
                "Call this when the user wants to change, edit, or modify a subscription."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subscription_id": {"type": "string"},
                    "bucket_id": {"type": "string"},
                    "name": {"type": "string"},
                    "provider_name": {"type": "string"},
                    "recurring_interval": {
                        "type": "string",
                        "enum": ["daily", "weekly", "monthly", "quarterly", "half-year", "yearly"],
                    },
                    "recurring_date": {"type": "string"},
                    "end_date": {
                        "type": "string",
                        "description": "Optional end date YYYY-MM-DD when billing stops. Omit if ongoing.",
                    },
                    "amount": {"type": "number"},
                    "currency": {"type": "string"},
                    "category_name": {"type": "string"},
                },
                "required": ["subscription_id", "bucket_id"],
            },
        },
    },
]

# Extra tool injected only when the user uploads a CSV file.
# The LLM itself parses the CSV, remaps columns, and calls this tool with
# clean, normalised data — no server-side CSV parsing needed.
_TOOL_CREATE_SUBSCRIPTIONS_BULK: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "create_subscriptions_bulk",
        "description": (
            "Create multiple subscriptions at once from data you have parsed and mapped yourself. "
            "When a CSV file is attached, inspect every column name and map it to the correct "
            "subscription field using your best judgment "
            "(e.g. 'price' → 'amount', 'service' → 'name', 'plan' → 'recurring_interval'). "
            "Normalize all values before calling: "
            "'Monthly' → 'monthly', '$9.99' → 9.99, strip currency symbols from amounts. "
            "Before calling this function, tell the user which column mapping you applied and any "
            "assumptions you made (e.g. 'No provider column found — using subscription name'). "
            "If a column's meaning is genuinely ambiguous and a reasonable guess is not possible, "
            "ask the user for clarification first. "
            "Do NOT ask the user to paste the file again — it is already available."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "bucket_id": {
                    "type": "string",
                    "description": "Exact bucket_id from the bucket list to import into.",
                },
                "subscriptions": {
                    "type": "array",
                    "description": "All rows from the CSV, already parsed and normalised.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Display name of the subscription.",
                            },
                            "provider_name": {
                                "type": "string",
                                "description": (
                                    "Provider / vendor name. "
                                    "Use the subscription name when no provider column exists."
                                ),
                            },
                            "recurring_interval": {
                                "type": "string",
                                "enum": ["daily", "weekly", "monthly", "quarterly", "half-year", "yearly"],
                                "description": "Billing frequency, normalised to one of the enum values.",
                            },
                            "recurring_date": {
                                "type": "string",
                                "description": "Last payment date in YYYY-MM-DD format. Omit if unavailable.",
                            },
                            "end_date": {
                                "type": "string",
                                "description": "Optional end date YYYY-MM-DD when billing stops. Omit if ongoing.",
                            },
                            "amount": {
                                "type": "number",
                                "description": "Price per billing interval as a plain number (no currency symbol).",
                            },
                            "currency": {
                                "type": "string",
                                "description": "ISO 4217 currency code, e.g. EUR, USD, GBP. Defaults to EUR.",
                            },
                            "category_name": {
                                "type": "string",
                                "description": "Category label. Omit if unavailable.",
                            },
                        },
                        "required": ["name", "recurring_interval", "amount"],
                    },
                },
            },
            "required": ["bucket_id", "subscriptions"],
        },
    },
}

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _get_settings(db: aiosqlite.Connection) -> dict[str, str]:
    cursor = await db.execute(
        "SELECT key, value FROM app_settings "
        "WHERE key IN ('ai_api_url', 'ai_api_key', 'ai_model')"
    )
    rows = await cursor.fetchall()
    return {row[0]: row[1] for row in rows}


async def _get_buckets(db: aiosqlite.Connection) -> list[dict[str, Any]]:
    cursor = await db.execute("SELECT id, name FROM buckets ORDER BY name")
    rows = await cursor.fetchall()
    return [{"id": row[0], "name": row[1]} for row in rows]


async def _get_subscriptions(db: aiosqlite.Connection) -> list[dict[str, Any]]:
    cursor = await db.execute(
        """
        SELECT s.id, s.bucket_id, b.name AS bucket_name,
               s.name, p.name AS provider_name, s.recurring_interval,
               s.amount, s.currency, c.name AS category_name
        FROM subscriptions s
        JOIN buckets b ON b.id = s.bucket_id
        LEFT JOIN providers p ON p.id = s.provider_id
        LEFT JOIN categories c ON c.id = s.category_id
        ORDER BY b.name, s.name
        """
    )
    rows = await cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in rows]


async def _ensure_provider(db: aiosqlite.Connection, name: str) -> int:
    await db.execute("INSERT OR IGNORE INTO providers (name) VALUES (?)", (name,))
    cursor = await db.execute("SELECT id FROM providers WHERE name = ?", (name,))
    row = await cursor.fetchone()
    return row[0]


async def _ensure_category(db: aiosqlite.Connection, name: str) -> int:
    await db.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
    cursor = await db.execute("SELECT id FROM categories WHERE name = ?", (name,))
    row = await cursor.fetchone()
    return row[0]


# ---------------------------------------------------------------------------
# Tool handlers — each opens its own DB connection
# ---------------------------------------------------------------------------


async def _tool_create_subscription(db_path: str, args: dict[str, Any]) -> dict[str, Any]:
    logger.info("Tool create_subscription: %s", args)
    bucket_id = args.get("bucket_id", "")

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")

        cursor = await db.execute("SELECT id FROM buckets WHERE id = ?", (bucket_id,))
        if not await cursor.fetchone():
            msg = f"Bucket '{bucket_id}' not found."
            logger.warning("create_subscription failed: %s", msg)
            return {"error": msg}

        provider_id = None
        if args.get("provider_name"):
            provider_id = await _ensure_provider(db, args["provider_name"])

        category_id = None
        if args.get("category_name"):
            category_id = await _ensure_category(db, args["category_name"])

        sub_id = secrets.token_hex(16)
        try:
            await db.execute(
                """
                INSERT INTO subscriptions
                    (id, bucket_id, name, provider_id, recurring_interval,
                     recurring_date, end_date, amount, currency, category_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sub_id,
                    bucket_id,
                    args["name"],
                    provider_id,
                    args["recurring_interval"],
                    args.get("recurring_date"),
                    args.get("end_date"),
                    float(args["amount"]),
                    args.get("currency", "EUR"),
                    category_id,
                ),
            )
            await db.commit()
            logger.info("create_subscription succeeded: id=%s name=%s", sub_id, args["name"])
        except Exception as exc:
            logger.exception("create_subscription DB error")
            return {"error": f"Database error: {exc}"}

    # Fire-and-forget logo fetch (outside the DB context so the connection is free)
    provider_name = args.get("provider_name") or args.get("name")
    if provider_name:
        import asyncio
        from backend.services.logo_fetch import fetch_logo_url

        async def _fetch_and_store() -> None:
            url = await fetch_logo_url(provider_name)
            if url:
                async with aiosqlite.connect(db_path) as _db:
                    await _db.execute(
                        "UPDATE subscriptions SET image_url = ? WHERE id = ?",
                        (url, sub_id),
                    )
                    await _db.commit()
                logger.info("Logo stored for subscription %s: %s", sub_id, url)

        asyncio.create_task(_fetch_and_store())

    return {"id": sub_id, "name": args["name"], "created": True}


async def _tool_update_subscription(db_path: str, args: dict[str, Any]) -> dict[str, Any]:
    logger.info("Tool update_subscription: %s", args)
    sub_id = args.get("subscription_id", "")
    bucket_id = args.get("bucket_id", "")

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")

        cursor = await db.execute(
            "SELECT id FROM subscriptions WHERE id = ? AND bucket_id = ?",
            (sub_id, bucket_id),
        )
        if not await cursor.fetchone():
            msg = f"Subscription '{sub_id}' not found in bucket '{bucket_id}'."
            logger.warning("update_subscription failed: %s", msg)
            return {"error": msg}

        updates: list[tuple[str, Any]] = []
        if "name" in args:
            updates.append(("name", args["name"]))
        if "provider_name" in args:
            provider_id = await _ensure_provider(db, args["provider_name"])
            updates.append(("provider_id", provider_id))
        if "recurring_interval" in args:
            updates.append(("recurring_interval", args["recurring_interval"]))
        if "recurring_date" in args:
            updates.append(("recurring_date", args["recurring_date"]))
        if "end_date" in args:
            updates.append(("end_date", args["end_date"]))
        if "amount" in args:
            updates.append(("amount", float(args["amount"])))
        if "currency" in args:
            updates.append(("currency", args["currency"]))
        if "category_name" in args:
            category_id = await _ensure_category(db, args["category_name"])
            updates.append(("category_id", category_id))

        if updates:
            set_clause = ", ".join(f"{col} = ?" for col, _ in updates)
            values = [v for _, v in updates] + [sub_id]
            try:
                await db.execute(
                    f"UPDATE subscriptions SET {set_clause},"
                    f" updated_at = datetime('now') WHERE id = ?",
                    values,
                )
                await db.commit()
                logger.info("update_subscription succeeded: id=%s", sub_id)
            except Exception as exc:
                logger.exception("update_subscription DB error")
                return {"error": f"Database error: {exc}"}

    return {"id": sub_id, "updated": True}


async def _tool_create_subscriptions_bulk(
    db_path: str, args: dict[str, Any]
) -> dict[str, Any]:
    """
    Create multiple subscriptions from LLM-mapped data.

    The LLM is responsible for parsing the CSV, remapping column names, and
    normalising values.  This handler simply inserts the clean rows.
    """
    bucket_id = args.get("bucket_id", "")
    items: list[dict[str, Any]] = args.get("subscriptions") or []

    logger.info(
        "Tool create_subscriptions_bulk: bucket_id=%s count=%d",
        bucket_id, len(items),
    )

    imported = 0
    failed: list[dict] = []
    created_ids: list[tuple[str, str]] = []  # (sub_id, provider_or_name) for logo fetch

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")

        cursor = await db.execute("SELECT id FROM buckets WHERE id = ?", (bucket_id,))
        if not await cursor.fetchone():
            msg = f"Bucket '{bucket_id}' not found."
            logger.warning("create_subscriptions_bulk failed: %s", msg)
            return {"error": msg}

        for item in items:
            name = (item.get("name") or "").strip()
            if not name:
                failed.append({"name": "<unknown>", "error": "'name' is required"})
                continue

            try:
                provider_id = None
                if item.get("provider_name"):
                    provider_id = await _ensure_provider(db, item["provider_name"])

                category_id = None
                if item.get("category_name"):
                    category_id = await _ensure_category(db, item["category_name"])

                sub_id = secrets.token_hex(16)
                await db.execute(
                    """
                    INSERT INTO subscriptions
                        (id, bucket_id, name, provider_id, recurring_interval,
                         recurring_date, end_date, amount, currency, category_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sub_id,
                        bucket_id,
                        name,
                        provider_id,
                        item["recurring_interval"],
                        item.get("recurring_date") or None,
                        item.get("end_date") or None,
                        float(item["amount"]),
                        (item.get("currency") or "EUR").strip().upper(),
                        category_id,
                    ),
                )
                logo_name = item.get("provider_name") or name
                created_ids.append((sub_id, logo_name))
                imported += 1
            except Exception as exc:
                logger.exception("create_subscriptions_bulk DB error for '%s'", name)
                failed.append({"name": name, "error": str(exc)})

        await db.commit()

    logger.info(
        "create_subscriptions_bulk: %d imported, %d failed", imported, len(failed)
    )

    # Fire logo fetches for newly created subscriptions (fire-and-forget)
    if created_ids:
        import asyncio
        from backend.services.logo_fetch import fetch_logo_url

        async def _fetch_logos() -> None:
            for sub_id, provider_name in created_ids:
                url = await fetch_logo_url(provider_name)
                if url:
                    async with aiosqlite.connect(db_path) as logo_db:
                        await logo_db.execute(
                            "UPDATE subscriptions SET image_url = ? WHERE id = ?",
                            (url, sub_id),
                        )
                        await logo_db.commit()

        asyncio.create_task(_fetch_logos())

    return {"imported": imported, "failed": failed}


async def _dispatch_tool(
    db_path: str,
    name: str,
    arguments_json: str,
    csv_content: str | None = None,
) -> dict[str, Any]:
    """Parse arguments and dispatch to the correct tool handler."""
    try:
        args = json.loads(arguments_json)
    except json.JSONDecodeError as exc:
        logger.error("Invalid tool arguments JSON for %s: %s", name, exc)
        return {"error": f"Invalid arguments: {exc}"}

    try:
        if name == "create_subscription":
            return await _tool_create_subscription(db_path, args)
        if name == "update_subscription":
            return await _tool_update_subscription(db_path, args)
        if name == "create_subscriptions_bulk":
            return await _tool_create_subscriptions_bulk(db_path, args)
        logger.warning("Unknown tool requested: %s", name)
        return {"error": f"Unknown tool: {name}"}
    except Exception as exc:
        logger.exception("Unexpected error in tool %s", name)
        return {"error": f"Unexpected error: {exc}"}


# ---------------------------------------------------------------------------
# Streaming helper — accumulates a streaming response and handles tool calls
# ---------------------------------------------------------------------------


async def _run_streaming_call(
    client: AsyncOpenAI,
    model: str,
    messages: list[dict[str, Any]],
    db_path: str,
    use_tools: bool = True,
    tools: list[dict[str, Any]] | None = None,
    csv_content: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Make a single streaming chat-completion call.

    Yields SSE ``data:`` lines as content arrives.  If the model signals
    ``finish_reason="tool_calls"``, executes the tools and recurses for the
    follow-up reply (tools disabled on recursion to prevent infinite loops).

    Parameters
    ----------
    tools:
        Tool schemas to advertise.  Defaults to ``_TOOLS`` when *use_tools* is
        True and *tools* is not supplied.
    csv_content:
        Raw CSV text uploaded with the current message — passed through to
        the ``import_csv`` tool handler.
    """
    kwargs: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
    if use_tools:
        kwargs["tools"] = tools if tools is not None else _TOOLS

    try:
        stream = await client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
    except Exception as exc:
        logger.exception("OpenAI API error")
        yield f'data: {json.dumps({"content": f"⚠️ AI API error: {exc}"})}\n\n'
        return

    # Accumulators for a potential tool call
    tool_calls: dict[int, dict[str, Any]] = {}
    finish_reason: str | None = None
    assistant_content = ""

    try:
        async for chunk in stream:
            choice = chunk.choices[0]
            delta = choice.delta
            finish_reason = choice.finish_reason or finish_reason

            # Stream text content straight to the client
            if delta.content:
                assistant_content += delta.content
                yield f"data: {json.dumps({'content': delta.content})}\n\n"

            # Accumulate tool call deltas
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls:
                        tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc_delta.id:
                        tool_calls[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls[idx]["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_calls[idx]["arguments"] += tc_delta.function.arguments
    except Exception as exc:
        logger.exception("Error reading stream")
        yield f'data: {json.dumps({"content": f"⚠️ Stream error: {exc}"})}\n\n'
        return

    if finish_reason != "tool_calls" or not tool_calls:
        # Plain text response — nothing more to do
        return

    # ---- Execute tool calls ------------------------------------------------
    logger.info("finish_reason=tool_calls, %d call(s) to execute", len(tool_calls))

    # Append the assistant turn (with tool_calls) to messages
    messages.append(
        {
            "role": "assistant",
            "content": assistant_content or None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in (tool_calls[i] for i in sorted(tool_calls))
            ],
        }
    )

    for tc in (tool_calls[i] for i in sorted(tool_calls)):
        result = await _dispatch_tool(
            db_path, tc["name"], tc["arguments"], csv_content=csv_content
        )
        if "error" in result:
            logger.error("Tool %s error: %s", tc["name"], result["error"])
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result),
            }
        )

    # ---- Follow-up streaming call with tool results ------------------------
    async for chunk in _run_streaming_call(
        client, model, messages, db_path, use_tools=False, csv_content=csv_content
    ):
        yield chunk


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def stream_chat_response(
    message: str,
    user_id: str,
    db_path: str,
    history: list[dict[str, str]] | None = None,
    csv_content: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Stream chat response as SSE data lines.

    Yields ``'data: {"content": "…"}\\n\\n'`` chunks followed by
    ``'data: [DONE]\\n\\n'``.
    """
    if AsyncOpenAI is None:
        yield 'data: {"content": "OpenAI package not installed."}\n\n'
        yield "data: [DONE]\n\n"
        return

    from backend.config import settings as env_cfg

    # ------------------------------------------------------------------
    # 1. Read DB state (short-lived connection)
    # ------------------------------------------------------------------
    try:
        async with aiosqlite.connect(db_path) as db:
            db_settings = await _get_settings(db)
            buckets = await _get_buckets(db)
            subscriptions = await _get_subscriptions(db)
    except Exception as exc:
        logger.exception("Failed to read DB context for AI chat")
        yield f'data: {json.dumps({"content": f"⚠️ Could not load data: {exc}"})}\n\n'
        yield "data: [DONE]\n\n"
        return

    # ------------------------------------------------------------------
    # 2. Resolve AI config (DB overrides env; env is the default fallback)
    # ------------------------------------------------------------------
    api_url = db_settings.get("ai_api_url", "") or env_cfg.ai_api_url
    api_key = db_settings.get("ai_api_key", "") or env_cfg.ai_api_key or "none"
    model = db_settings.get("ai_model", "") or env_cfg.ai_model or "gpt-4o-mini"

    if not api_url:
        yield 'data: {"content": "AI is not configured. Set ai_api_url in Settings."}\n\n'
        yield "data: [DONE]\n\n"
        return

    # ------------------------------------------------------------------
    # 3. Build system prompt
    # ------------------------------------------------------------------
    if buckets:
        bucket_lines = "\n".join(f"- {b['name']} (bucket_id: {b['id']})" for b in buckets)
        bucket_context = f"Buckets:\n{bucket_lines}"
    else:
        bucket_context = "The user has no buckets yet."

    if subscriptions:
        sub_lines = "\n".join(
            f"- [{s['bucket_name']}] {s['name']}"
            f" (id: {s['id']}, bucket_id: {s['bucket_id']})"
            f" | {s['provider_name'] or 'no provider'}"
            f" | {s['amount']} {s['currency']}/{s['recurring_interval']}"
            + (f" | [{s['category_name']}]" if s["category_name"] else "")
            for s in subscriptions
        )
        sub_context = f"Current subscriptions:\n{sub_lines}"
    else:
        sub_context = "The user has no subscriptions yet."

    csv_rule = (
        "- A CSV file has been attached. To import it:\n"
        "  1. Inspect every column name and map it to the correct subscription field\n"
        "     (e.g. 'price' → 'amount', 'service' → 'name', 'plan' → 'recurring_interval').\n"
        "  2. Normalise all values: 'Monthly' → 'monthly', '$9.99' → 9.99, strip symbols.\n"
        "  3. Tell the user which mapping you applied and any assumptions you made\n"
        "     (e.g. 'No provider column — using subscription name as provider').\n"
        "  4. If a column's meaning is genuinely ambiguous, ask the user before importing.\n"
        "  5. Once confident (or after the user confirms), call create_subscriptions_bulk\n"
        "     with the full parsed list.\n"
        "  The file content is already available — do not ask the user to paste it again."
        if csv_content
        else ""
    )
    system_prompt = "\n".join(filter(None, [
        "You are SubControl, an AI assistant for managing subscriptions.",
        "",
        "## Rules",
        "- To ADD a subscription: call create_subscription. Use the exact bucket_id from the bucket list.",
        "- To CHANGE a subscription: call update_subscription. Use the exact id and bucket_id from the subscription list.",
        csv_rule,
        "- NEVER describe or pretend to perform an action — always call the function.",
        "- After a successful function call, confirm briefly what was done.",
        "- If a function returns an error, report it clearly to the user.",
        "- For questions or analysis, respond directly without calling a function.",
        "",
        bucket_context,
        "",
        sub_context,
    ]))

    # ------------------------------------------------------------------
    # 4. Assemble message list and stream
    # ------------------------------------------------------------------
    # When a CSV file is attached, prepend its content to the user message so
    # the model can see the data while deciding which bucket to import into.
    if csv_content:
        user_content = (
            f"[Attached CSV file]\n```csv\n{csv_content.strip()}\n```\n\n{message}"
            if message.strip()
            else f"[Attached CSV file]\n```csv\n{csv_content.strip()}\n```"
        )
    else:
        user_content = message

    chat_messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        *(history or []),
        {"role": "user", "content": user_content},
    ]

    # Build the active tool list: base tools + bulk creator when a CSV is present
    active_tools = _TOOLS + ([_TOOL_CREATE_SUBSCRIPTIONS_BULK] if csv_content else [])

    logger.debug(
        "Starting stream: model=%s history_len=%d csv=%s",
        model, len(history or []), bool(csv_content),
    )

    client = AsyncOpenAI(base_url=api_url, api_key=api_key)
    async for chunk in _run_streaming_call(
        client, model, chat_messages, db_path,
        tools=active_tools, csv_content=csv_content,
    ):
        yield chunk

    yield "data: [DONE]\n\n"

"""
Chat router — POST /api/chat/message, conversation CRUD.

Streams SSE response from the AI chat service. Conversations and messages
are persisted per user so the AI Chat page can list and reopen past
conversations.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Literal

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.database import get_db, get_db_path
from backend.dependencies import CurrentUser, get_current_user
from backend.services.ai_chat import stream_chat_response

router = APIRouter(prefix="/api/chat", tags=["chat"])


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[HistoryMessage] = []
    bucket_id: str | None = None
    csv_content: str | None = None  # raw text of an attached CSV file
    conversation_id: str | None = None  # omit to start a new conversation


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: str


class ConversationDetail(ConversationSummary):
    messages: list[ConversationMessage]


# ---------------------------------------------------------------------------
# Persistence helpers
#
# Each opens its own short-lived connection rather than reusing the shared
# request-scoped one — matching ai_chat.py's approach, which avoids the
# yield-dependency / StreamingResponse timing bug where the connection is
# closed before a generator finishes executing writes.
# ---------------------------------------------------------------------------


async def _create_conversation(db_path: str, user_id: str, title: str) -> str:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "INSERT INTO chat_conversations (user_id, title) VALUES (?, ?) RETURNING id",
            (user_id, title),
        ) as cur:
            row = await cur.fetchone()
        await db.commit()
        return row["id"]


async def _save_message(db_path: str, conversation_id: str, role: str, content: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO chat_messages (conversation_id, role, content) VALUES (?, ?, ?)",
            (conversation_id, role, content),
        )
        await db.execute(
            "UPDATE chat_conversations SET updated_at = datetime('now') WHERE id = ?",
            (conversation_id,),
        )
        await db.commit()


def _make_title(message: str) -> str:
    text = " ".join(message.strip().split())
    if not text:
        return "New conversation"
    return text[:60] + ("…" if len(text) > 60 else "")


async def _persist_and_relay(
    chunks: AsyncGenerator[str, None],
    db_path: str,
    conversation_id: str,
) -> AsyncGenerator[str, None]:
    """Forward every SSE line unchanged; once the stream completes, persist
    the accumulated assistant reply as a single message."""
    assistant_content = ""
    async for line in chunks:
        if line.startswith("data: "):
            data = line[len("data: "):].strip()
            if data == "[DONE]":
                if assistant_content:
                    await _save_message(db_path, conversation_id, "assistant", assistant_content)
                yield line
                continue
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict) and "content" in parsed:
                assistant_content += parsed["content"]
        yield line


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/message")
async def chat_message(
    payload: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """Send a chat message and receive a streaming SSE response."""
    db_path = get_db_path()
    history = [{"role": m.role, "content": m.content} for m in payload.history]

    conversation_id = payload.conversation_id
    if not conversation_id:
        conversation_id = await _create_conversation(
            db_path, current_user.id, _make_title(payload.message)
        )
    await _save_message(db_path, conversation_id, "user", payload.message)

    chunks = stream_chat_response(
        payload.message,
        current_user.id,
        db_path,
        history,
        csv_content=payload.csv_content,
        is_admin=current_user.is_admin,
    )

    return StreamingResponse(
        _persist_and_relay(chunks, db_path, conversation_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Conversation-Id": conversation_id,
        },
    )


@router.get("/conversations")
async def list_conversations(
    current_user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[ConversationSummary]:
    async with db.execute(
        """
        SELECT id, title, created_at, updated_at FROM chat_conversations
        WHERE user_id = ?
        ORDER BY updated_at DESC
        LIMIT 50
        """,
        (current_user.id,),
    ) as cur:
        rows = await cur.fetchall()
    return [ConversationSummary(**dict(row)) for row in rows]


async def _get_conversation_or_404(
    conversation_id: str, user_id: str, db: aiosqlite.Connection
) -> aiosqlite.Row:
    async with db.execute(
        """
        SELECT id, title, created_at, updated_at FROM chat_conversations
        WHERE id = ? AND user_id = ?
        """,
        (conversation_id, user_id),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return row


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> ConversationDetail:
    conv = await _get_conversation_or_404(conversation_id, current_user.id, db)
    async with db.execute(
        """
        SELECT role, content, created_at FROM chat_messages
        WHERE conversation_id = ?
        ORDER BY created_at ASC, rowid ASC
        """,
        (conversation_id,),
    ) as cur:
        rows = await cur.fetchall()
    return ConversationDetail(
        **dict(conv),
        messages=[ConversationMessage(**dict(r)) for r in rows],
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> None:
    await _get_conversation_or_404(conversation_id, current_user.id, db)
    await db.execute("DELETE FROM chat_conversations WHERE id = ?", (conversation_id,))
    await db.commit()

"""
Chat router — POST /api/chat/message

Streams SSE response from the AI chat service.
"""

from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.database import get_db_path
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


@router.post("/message")
async def chat_message(
    payload: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """Send a chat message and receive a streaming SSE response."""
    db_path = get_db_path()
    history = [{"role": m.role, "content": m.content} for m in payload.history]
    return StreamingResponse(
        stream_chat_response(
            payload.message,
            current_user.id,
            db_path,
            history,
            csv_content=payload.csv_content,
            is_admin=current_user.is_admin,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

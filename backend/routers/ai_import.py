"""
AI document import router — upload a policy PDF or a photo/screenshot and
get back proposed subscription/insurance records for the user to review.

Routes
------
POST /api/buckets/{bucket_id}/ai-import/extract   Extract records from a document

The uploaded file is read into memory only and never persisted to disk —
extraction is a read-only preview. Nothing is created until the frontend
calls the existing subscription/insurance create endpoints (and, for
insurances, the attachment-upload endpoint with the same file) after the
user explicitly confirms which proposed records to keep.
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from backend.database import get_db
from backend.dependencies import CurrentUser, get_current_user
from backend.routers.subscriptions import _check_bucket_access, _get_bucket_or_404
from backend.services.ai_extract import extract_records_from_document, resolve_ai_config
from backend.services.attachments import MAX_ATTACHMENT_BYTES

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ai-import"])

_ALLOWED_EXTRACT_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}

# Cap how much extracted PDF text is sent to the model — long documents are
# truncated rather than blowing up the prompt (and the token bill).
_MAX_PDF_TEXT_CHARS = 20_000


class ExtractedRecord(BaseModel):
    type: str
    confidence: str
    fields: dict[str, Any]


class ExtractResponse(BaseModel):
    records: list[ExtractedRecord]


def _extract_pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as exc:
        raise HTTPException(status_code=422, detail=f"Couldn't read this PDF: {exc}") from exc
    return "\n".join(pages)


@router.post(
    "/api/buckets/{bucket_id}/ai-import/extract",
    response_model=ExtractResponse,
)
async def extract_from_document(
    bucket_id: str,
    file: UploadFile,
    user: CurrentUser = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> ExtractResponse:
    await _get_bucket_or_404(bucket_id, db)
    await _check_bucket_access(bucket_id, user, db)

    config = await resolve_ai_config(db)
    if config is None:
        raise HTTPException(
            status_code=400, detail="AI is not configured. Set it up in Settings."
        )

    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTRACT_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Upload a PDF or an image (PNG/JPG).",
        )

    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB)")

    if ext == ".pdf":
        text = _extract_pdf_text(data)
        if len(text.strip()) < 50:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Couldn't read text from this PDF — it may be a scanned "
                    "image. Try uploading a photo or screenshot instead."
                ),
            )
        content: dict[str, str] = {"kind": "text", "text": text[:_MAX_PDF_TEXT_CHARS]}
    else:
        content_type = file.content_type or f"image/{ext.lstrip('.')}"
        b64 = base64.b64encode(data).decode("ascii")
        content = {"kind": "image", "data_url": f"data:{content_type};base64,{b64}"}

    records = await extract_records_from_document(content, config)
    return ExtractResponse(records=[ExtractedRecord(**r) for r in records])

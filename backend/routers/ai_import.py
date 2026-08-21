"""
AI document import router — upload a policy PDF or a photo/screenshot and
get back proposed subscription/insurance records for the user to review.

Routes
------
POST /api/buckets/{bucket_id}/ai-import/extract   Extract records from a document

PDFs are handled two ways: if they have a text layer, the extracted text is
sent to the model directly; if not (e.g. a scanned letter saved as PDF, with
no text layer at all), the first few pages are rendered to images instead
and sent through the same vision path used for photo/screenshot uploads —
so image-only PDFs are supported without requiring OCR or a separate upload.
See backend.services.document_content for that logic (shared with the
attachment-upload "analyze against existing record" flow).

The uploaded file is read into memory only and never persisted to disk —
extraction is a read-only preview. Nothing is created until the frontend
calls the existing subscription/insurance create endpoints (and, for
insurances, the attachment-upload endpoint with the same file) after the
user explicitly confirms which proposed records to keep.
"""

from __future__ import annotations

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
from backend.services.document_content import (
    ALLOWED_ANALYSIS_EXTENSIONS,
    prepare_document_content,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ai-import"])


class ExtractedRecord(BaseModel):
    type: str
    confidence: str
    fields: dict[str, Any]


class ExtractResponse(BaseModel):
    records: list[ExtractedRecord]


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
    if ext not in ALLOWED_ANALYSIS_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Upload a PDF or an image (PNG/JPG).",
        )

    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB)")

    content = await prepare_document_content(file.filename or "", file.content_type, data)
    if content is None:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Upload a PDF or an image (PNG/JPG).",
        )

    records = await extract_records_from_document(content, config)
    return ExtractResponse(records=[ExtractedRecord(**r) for r in records])

"""
Shared document-content preparation for AI analysis.

Converts an uploaded file's raw bytes into the ``content`` dict shape
``backend.services.ai_extract`` expects (either extracted text or one or
more page images for a vision call). Used by both the standalone AI
document-import endpoint and the attachment-upload "analyze against
existing record" flow, so the PDF-text-vs-scanned-image branching logic
lives in exactly one place.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

from fastapi import HTTPException

ALLOWED_ANALYSIS_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}

# Cap how much extracted PDF text is sent to the model — long documents are
# truncated rather than blowing up the prompt (and the token bill).
_MAX_PDF_TEXT_CHARS = 20_000

# When a PDF has no (or negligible) extractable text, it's likely a scanned
# letter/photo embedded as an image — render pages to images and use vision
# instead of rejecting it. Capped at a few pages: letters/invoices are
# almost always 1 page, and this bounds prompt size/cost for anything longer.
_MAX_RENDERED_PDF_PAGES = 3
_PDF_RENDER_SCALE = 2.0  # ~144 DPI — enough detail for OCR-by-vision


def _extract_pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as exc:
        raise HTTPException(status_code=422, detail=f"Couldn't read this PDF: {exc}") from exc
    return "\n".join(pages)


def _render_pdf_pages_as_images(
    data: bytes, *, max_pages: int = _MAX_RENDERED_PDF_PAGES, scale: float = _PDF_RENDER_SCALE
) -> list[str]:
    """
    Render the first *max_pages* pages of a PDF to PNG data URLs.

    No system dependencies (poppler etc.) required — pypdfium2 bundles its
    own PDF renderer.
    """
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(data)
        page_count = len(pdf)
        data_urls = []
        for i in range(min(page_count, max_pages)):
            bitmap = pdf[i].render(scale=scale)
            buf = io.BytesIO()
            bitmap.to_pil().save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            data_urls.append(f"data:image/png;base64,{b64}")
        return data_urls
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Couldn't read this PDF: {exc}") from exc


async def prepare_document_content(
    filename: str, content_type: str | None, data: bytes
) -> dict[str, Any] | None:
    """
    Build an ``ai_extract``-ready content dict from an uploaded file's bytes.

    Returns ``{"kind": "text", "text": "..."}`` for a PDF with a real text
    layer, ``{"kind": "image", "data_urls": [...]}`` for an image upload or
    a scanned/image-only PDF (rendered to page images), or ``None`` if the
    file type isn't analyzable (e.g. ``.doc``/``.docx`` — still fine as a
    plain attachment, just not run through AI).
    """
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_ANALYSIS_EXTENSIONS:
        return None

    if ext == ".pdf":
        text = _extract_pdf_text(data)
        if len(text.strip()) < 50:
            data_urls = _render_pdf_pages_as_images(data)
            if not data_urls:
                raise HTTPException(
                    status_code=422, detail="Couldn't extract any pages from this PDF."
                )
            return {"kind": "image", "data_urls": data_urls}
        return {"kind": "text", "text": text[:_MAX_PDF_TEXT_CHARS]}

    resolved_content_type = content_type or f"image/{ext.lstrip('.')}"
    b64 = base64.b64encode(data).decode("ascii")
    return {"kind": "image", "data_urls": [f"data:{resolved_content_type};base64,{b64}"]}

"""
File storage for insurance attachments (e.g. policy conditions documents).

Files are written to disk under a directory next to the SQLite database file,
so they live inside the same Docker volume (``./data``) without requiring any
extra configuration or compose changes. Only metadata (filename, content
type, size, storage path) is kept in the database.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from backend.database import get_db_path

MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024  # 20 MB

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx"}

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def attachments_dir() -> Path:
    """Root directory for all stored attachments, alongside the SQLite DB file."""
    return Path(get_db_path()).parent / "attachments"


def _sanitize_filename(filename: str) -> str:
    name = Path(filename).name  # strip any path components
    name = _UNSAFE_CHARS.sub("_", name)
    return name or "file"


async def save_attachment(insurance_id: str, upload_file: UploadFile) -> tuple[str, str, int]:
    """
    Persist *upload_file* to disk for *insurance_id*.

    Returns ``(storage_path, sanitized_filename, size_bytes)`` where
    ``storage_path`` is relative to :func:`attachments_dir`.

    Raises ``HTTPException`` (413/415) on oversized or disallowed files.
    """
    original_name = upload_file.filename or "file"
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    content = await upload_file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB)")

    sanitized = _sanitize_filename(original_name)
    attachment_id = uuid.uuid4().hex
    stored_name = f"{attachment_id}_{sanitized}"

    insurance_dir = attachments_dir() / insurance_id
    insurance_dir.mkdir(parents=True, exist_ok=True)

    dest = insurance_dir / stored_name
    dest.write_bytes(content)

    storage_path = f"{insurance_id}/{stored_name}"
    return storage_path, sanitized, len(content)


def delete_attachment_file(storage_path: str) -> None:
    """Remove the file at *storage_path* (relative to attachments_dir()), if present."""
    path = attachments_dir() / storage_path
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass

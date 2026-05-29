from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

UPLOAD_ROOT = Path(os.getenv("UPLOAD_ROOT", "uploads"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}
ALLOWED_PDF_TYPES = {"application/pdf"}
ALLOWED_DOCUMENT_TYPES = ALLOWED_PDF_TYPES | {
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}
ALLOWED_GENERAL_UPLOAD_TYPES = ALLOWED_IMAGE_TYPES | ALLOWED_DOCUMENT_TYPES


def _safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", base)
    return cleaned[:200] or "file"


def ensure_upload_root() -> Path:
    root = UPLOAD_ROOT.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_upload_file(
    file: UploadFile,
    *,
    subdir: str,
    allowed_mime: set[str],
) -> tuple[str, str, int]:
    if not file.content_type or file.content_type not in allowed_mime:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}",
        )

    root = ensure_upload_root()
    target_dir = root / subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(_safe_filename(file.filename or "file")).suffix
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    relative_path = f"{subdir}/{stored_name}"
    absolute_path = root / relative_path

    size = 0
    with absolute_path.open("wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                absolute_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds {MAX_UPLOAD_BYTES} bytes",
                )
            out.write(chunk)

    return relative_path.replace("\\", "/"), file.content_type, size


def resolve_upload_path(relative_path: str) -> Path:
    root = ensure_upload_root().resolve()
    full = (root / relative_path).resolve()
    if not str(full).startswith(str(root)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path")
    if not full.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return full

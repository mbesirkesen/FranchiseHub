from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from .security import ALGORITHM, SECRET_KEY, utc_now

DOWNLOAD_TOKEN_EXPIRE_MINUTES = int(os.getenv("DOWNLOAD_TOKEN_EXPIRE_MINUTES", "15"))
PUBLIC_API_BASE_URL = os.getenv(
    "PUBLIC_API_BASE_URL", "http://127.0.0.1:8000"
).rstrip("/")


def create_fdd_download_token(*, brand_id: int, fdd_id: int) -> tuple[str, datetime]:
    expires_at = utc_now() + timedelta(minutes=DOWNLOAD_TOKEN_EXPIRE_MINUTES)
    payload = {
        "typ": "fdd_download",
        "brand_id": brand_id,
        "fdd_id": fdd_id,
        "exp": expires_at,
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token, expires_at


def decode_fdd_download_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("typ") != "fdd_download":
        raise JWTError("Invalid token type")
    return payload


def build_fdd_download_url(*, brand_id: int, fdd_id: int, token: str) -> str:
    return f"{PUBLIC_API_BASE_URL}/files/fdd/download?token={token}"


def build_media_public_url(media_id: int) -> str:
    return f"{PUBLIC_API_BASE_URL}/files/media/{media_id}"


def build_owner_document_url(document_id: int) -> str:
    return f"{PUBLIC_API_BASE_URL}/files/owner-documents/{document_id}"


def build_uploaded_file_url(file_id: int) -> str:
    return f"{PUBLIC_API_BASE_URL}/files/uploads/{file_id}"

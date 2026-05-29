import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from .models import UserRole

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
PASSWORD_RESET_EXPIRE_MINUTES = int(os.getenv("PASSWORD_RESET_EXPIRE_MINUTES", "60"))
EMAIL_VERIFY_EXPIRE_MINUTES = int(os.getenv("EMAIL_VERIFY_EXPIRE_MINUTES", "1440"))


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject_id: int,
    role: UserRole,
    expires_delta: Optional[timedelta] = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode = {
        "sub": f"{role.value}:{subject_id}",
        "subject_id": subject_id,
        "role": role.value,
        "exp": expire,
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def parse_jwt_error(exc: JWTError) -> str:
    return str(exc) or "Invalid token"


def generate_opaque_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def generate_email_verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_opaque_token(token: str) -> str:
    digest = hashlib.sha256(f"{token}:{SECRET_KEY}".encode()).hexdigest()
    return digest


def verify_opaque_token(token: str, token_hash: str) -> bool:
    return secrets.compare_digest(hash_opaque_token(token), token_hash)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

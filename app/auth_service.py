from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Optional, Tuple, Union

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import AuthToken, AuthTokenType, Buyer, FranchiseOwner, UserRole
from .schemas import (
    AuthMeResponse,
    AuthenticatedPrincipal,
    BuyerRead,
    FranchiseOwnerRead,
    MeUpdate,
)
from .security import (
    EMAIL_VERIFY_EXPIRE_MINUTES,
    PASSWORD_RESET_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    generate_email_verification_code,
    generate_opaque_token,
    hash_opaque_token,
    normalize_email,
    utc_now,
    verify_opaque_token,
)

_log = logging.getLogger(__name__)

Account = Union[Buyer, FranchiseOwner]
AccountWithRole = Tuple[UserRole, Account]


def expose_reset_token_in_response() -> bool:
    return os.getenv("EXPOSE_AUTH_TOKENS_IN_RESPONSE", "").lower() in (
        "1",
        "true",
        "yes",
    )


def find_account_by_email(db: Session, email: str) -> Optional[AccountWithRole]:
    email = normalize_email(email)
    buyer = db.scalar(select(Buyer).where(Buyer.email == email))
    if buyer:
        return UserRole.buyer, buyer
    owner = db.scalar(select(FranchiseOwner).where(FranchiseOwner.email == email))
    if owner:
        return UserRole.franchise_owner, owner
    return None


def load_account(db: Session, role: UserRole, subject_id: int) -> Optional[Account]:
    if role == UserRole.buyer:
        return db.get(Buyer, subject_id)
    if role == UserRole.franchise_owner:
        return db.get(FranchiseOwner, subject_id)
    return None


def _invalidate_active_tokens(
    db: Session,
    *,
    token_type: AuthTokenType,
    role: UserRole,
    subject_id: int,
) -> None:
    now = utc_now()
    rows = db.scalars(
        select(AuthToken).where(
            AuthToken.token_type == token_type,
            AuthToken.role == role,
            AuthToken.subject_id == subject_id,
            AuthToken.used_at.is_(None),
            AuthToken.expires_at > now,
        )
    ).all()
    for row in rows:
        row.used_at = now


def _store_token(
    db: Session,
    *,
    token_type: AuthTokenType,
    role: UserRole,
    subject_id: int,
    email: str,
    plain_token: str,
    expires_delta: timedelta,
) -> AuthToken:
    record = AuthToken(
        token_type=token_type,
        token_hash=hash_opaque_token(plain_token),
        role=role,
        subject_id=subject_id,
        email=email,
        expires_at=utc_now() + expires_delta,
    )
    db.add(record)
    return record


def issue_refresh_token(db: Session, role: UserRole, account: Account) -> str:
    _invalidate_active_tokens(
        db, token_type=AuthTokenType.refresh, role=role, subject_id=account.id
    )
    plain = generate_opaque_token()
    _store_token(
        db,
        token_type=AuthTokenType.refresh,
        role=role,
        subject_id=account.id,
        email=account.email,
        plain_token=plain,
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.commit()
    return plain


def issue_email_verification(db: Session, role: UserRole, account: Account) -> str:
    _invalidate_active_tokens(
        db, token_type=AuthTokenType.email_verify, role=role, subject_id=account.id
    )
    code = generate_email_verification_code()
    _store_token(
        db,
        token_type=AuthTokenType.email_verify,
        role=role,
        subject_id=account.id,
        email=account.email,
        plain_token=code,
        expires_delta=timedelta(minutes=EMAIL_VERIFY_EXPIRE_MINUTES),
    )
    db.commit()
    _log.info(
        "Email verification code for %s (%s:%s): %s",
        account.email,
        role.value,
        account.id,
        code,
    )
    return code


def issue_password_reset(db: Session, role: UserRole, account: Account) -> str:
    _invalidate_active_tokens(
        db, token_type=AuthTokenType.password_reset, role=role, subject_id=account.id
    )
    plain = generate_opaque_token()
    _store_token(
        db,
        token_type=AuthTokenType.password_reset,
        role=role,
        subject_id=account.id,
        email=account.email,
        plain_token=plain,
        expires_delta=timedelta(minutes=PASSWORD_RESET_EXPIRE_MINUTES),
    )
    db.commit()
    _log.info(
        "Password reset token for %s (%s:%s): %s",
        account.email,
        role.value,
        account.id,
        plain,
    )
    return plain


def consume_token(
    db: Session,
    *,
    plain_token: str,
    token_type: AuthTokenType,
    email: Optional[str] = None,
) -> AuthToken:
    token_hash = hash_opaque_token(plain_token)
    now = utc_now()
    record = db.scalar(
        select(AuthToken).where(
            AuthToken.token_hash == token_hash,
            AuthToken.token_type == token_type,
            AuthToken.used_at.is_(None),
            AuthToken.expires_at > now,
        )
    )
    if record is None or not verify_opaque_token(plain_token, record.token_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )
    if email is not None and record.email != email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )
    record.used_at = now
    db.add(record)
    return record


def build_auth_me_response(role: UserRole, account: Account) -> AuthMeResponse:
    verified = bool(getattr(account, "email_verified", False))
    if role == UserRole.buyer:
        return AuthMeResponse(
            role=role,
            email_verified=verified,
            buyer=BuyerRead.model_validate(account),
        )
    return AuthMeResponse(
        role=role,
        email_verified=verified,
        franchise_owner=FranchiseOwnerRead.model_validate(account),
    )


def apply_me_update(account: Account, role: UserRole, payload: MeUpdate) -> None:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return

    if role == UserRole.buyer:
        allowed = {
            "phone",
            "first_name",
            "last_name",
            "city",
            "investment_budget",
            "experience_years",
            "preferred_sector",
            "identity_number",
        }
    else:
        allowed = {
            "phone",
            "company_name",
            "authorized_person_name",
            "country",
            "city",
            "company_address",
            "website",
        }

    unknown = set(data) - allowed
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Fields not allowed for role {role.value}: {sorted(unknown)}",
        )

    for key, value in data.items():
        setattr(account, key, value)


def ensure_active_account(account: Account) -> None:
    if not account.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )


def login_tokens(db: Session, role: UserRole, account: Account) -> tuple[str, str]:
    from .security import create_access_token

    ensure_active_account(account)
    access = create_access_token(subject_id=account.id, role=role)
    refresh = issue_refresh_token(db, role, account)
    return access, refresh


def principal_to_account(
    db: Session, principal: AuthenticatedPrincipal
) -> Tuple[UserRole, Account]:
    account = load_account(db, principal.role, principal.user_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return principal.role, account

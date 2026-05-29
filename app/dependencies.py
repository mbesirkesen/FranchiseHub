from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from .database import get_db
from .models import Buyer, FranchiseOwner, UserRole
from .schemas import AuthenticatedPrincipal
from .security import decode_access_token


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _resolve_principal(db: Session, role: UserRole, subject_id: int) -> AuthenticatedPrincipal | None:
    if role == UserRole.buyer:
        user = db.get(Buyer, subject_id)
    elif role == UserRole.franchise_owner:
        user = db.get(FranchiseOwner, subject_id)
    else:
        return None

    if user is None:
        return None
    return AuthenticatedPrincipal(role=role, user_id=user.id, email=user.email)


def get_current_principal(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> AuthenticatedPrincipal:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        subject_id_raw = payload.get("subject_id")
        role_raw = payload.get("role")
        if subject_id_raw is None or role_raw is None:
            raise credentials_exception
        subject_id = int(subject_id_raw)
        role = UserRole(role_raw)
    except (JWTError, ValueError):
        raise credentials_exception

    principal = _resolve_principal(db, role, subject_id)
    if principal is None:
        raise credentials_exception

    if role == UserRole.buyer:
        account = db.get(Buyer, subject_id)
    elif role == UserRole.franchise_owner:
        account = db.get(FranchiseOwner, subject_id)
    else:
        raise credentials_exception
    if account is None or not account.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    return principal


def require_roles(*roles: UserRole) -> Callable:
    def role_checker(
        current_user: AuthenticatedPrincipal = Depends(get_current_principal),
    ) -> AuthenticatedPrincipal:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource",
            )
        return current_user

    return role_checker

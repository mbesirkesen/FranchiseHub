from __future__ import annotations

from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth_service import (
    apply_me_update,
    build_auth_me_response,
    consume_token,
    expose_reset_token_in_response,
    find_account_by_email,
    issue_email_verification,
    issue_password_reset,
    issue_refresh_token,
    login_tokens,
    principal_to_account,
)
from ..database import get_db
from ..dependencies import get_current_principal
from ..models import AuthTokenType, Buyer, FranchiseOwner, UserRole
from ..schemas import (
    AuthMeResponse,
    AuthenticatedPrincipal,
    BuyerCreate,
    BuyerRead,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    FranchiseOwnerCreate,
    FranchiseOwnerRead,
    MeUpdate,
    MessageResponse,
    RefreshTokenRequest,
    ResetPasswordRequest,
    Token,
    UserLogin,
    VerifyEmailRequest,
)
from ..security import create_access_token, hash_password, normalize_email, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

_FORGOT_PASSWORD_MSG = (
    "If an account exists for this email, password reset instructions have been sent."
)


def _email_exists(db: Session, email: str) -> bool:
    email = normalize_email(email)
    buyer_exists = db.scalar(select(Buyer.id).where(Buyer.email == email))
    owner_exists = db.scalar(select(FranchiseOwner.id).where(FranchiseOwner.email == email))
    return bool(buyer_exists or owner_exists)


def _after_register(db: Session, role: UserRole, account: Buyer | FranchiseOwner) -> None:
    issue_email_verification(db, role, account)


@router.post("/register/buyer", response_model=BuyerRead, status_code=status.HTTP_201_CREATED)
def register_buyer(payload: BuyerCreate, db: Session = Depends(get_db)):
    if _email_exists(db, payload.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered",
        )

    user = Buyer(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        city=payload.city,
        investment_budget=payload.investment_budget,
        experience_years=payload.experience_years,
        preferred_sector=payload.preferred_sector,
        identity_number=payload.identity_number,
        email_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _after_register(db, UserRole.buyer, user)
    return user


@router.post(
    "/register/franchise-owner",
    response_model=FranchiseOwnerRead,
    status_code=status.HTTP_201_CREATED,
)
def register_franchise_owner(
    payload: FranchiseOwnerCreate,
    db: Session = Depends(get_db),
):
    if _email_exists(db, payload.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered",
        )

    owner = FranchiseOwner(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        company_name=payload.company_name,
        tax_number=payload.tax_number,
        phone=payload.phone,
        authorized_person_name=payload.authorized_person_name,
        country=payload.country,
        city=payload.city,
        company_address=payload.company_address,
        website=payload.website,
        verification_status=payload.verification_status,
        email_verified=False,
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)
    _after_register(db, UserRole.franchise_owner, owner)
    return owner


@router.post("/login", response_model=Token)
async def login(request: Request, db: Session = Depends(get_db)):
    ct = (request.headers.get("content-type") or "").lower()
    email_raw = None
    password_raw = None

    if "multipart/form-data" in ct:
        form = await request.form()
        ev, uv = form.get("email"), form.get("username")
        email_raw = ev if ev not in (None, "") else uv
        password_raw = form.get("password")
    elif "application/x-www-form-urlencoded" in ct:
        body = await request.body()
        q = parse_qs(body.decode(errors="replace"), keep_blank_values=True)
        ev = (q.get("email") or [None])[0]
        uv = (q.get("username") or [None])[0]
        email_raw = ev if ev not in (None, "") else uv
        password_raw = (q.get("password") or [None])[0]
    else:
        try:
            data = await request.json()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Body must be JSON with email and password",
            ) from exc
        if not isinstance(data, dict):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="JSON body must be an object",
            )
        email_raw = data.get("email")
        password_raw = data.get("password")

    if email_raw is None or password_raw is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="email (or username) and password are required",
        )
    try:
        payload = UserLogin.model_validate(
            {"email": str(email_raw).strip(), "password": str(password_raw)}
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc

    found = find_account_by_email(db, payload.email)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    role, account = found
    if not verify_password(payload.password, account.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token, refresh_token = login_tokens(db, role, account)
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    reset_token = None
    found = find_account_by_email(db, payload.email)
    if found:
        role, account = found
        plain = issue_password_reset(db, role, account)
        if expose_reset_token_in_response():
            reset_token = plain
    return ForgotPasswordResponse(message=_FORGOT_PASSWORD_MSG, reset_token=reset_token)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    record = consume_token(
        db, plain_token=payload.token, token_type=AuthTokenType.password_reset
    )
    account = None
    if record.role == UserRole.buyer:
        account = db.get(Buyer, record.subject_id)
    elif record.role == UserRole.franchise_owner:
        account = db.get(FranchiseOwner, record.subject_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )
    account.hashed_password = hash_password(payload.new_password)
    db.add(account)
    db.commit()
    return MessageResponse(message="Password has been reset")


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    record = consume_token(
        db,
        plain_token=payload.code,
        token_type=AuthTokenType.email_verify,
        email=payload.email,
    )
    account = None
    if record.role == UserRole.buyer:
        account = db.get(Buyer, record.subject_id)
    elif record.role == UserRole.franchise_owner:
        account = db.get(FranchiseOwner, record.subject_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )
    account.email_verified = True
    db.add(account)
    db.commit()
    return MessageResponse(message="Email verified successfully")


@router.post("/refresh", response_model=Token)
def refresh_tokens(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    record = consume_token(
        db, plain_token=payload.refresh_token, token_type=AuthTokenType.refresh
    )
    account = None
    if record.role == UserRole.buyer:
        account = db.get(Buyer, record.subject_id)
    elif record.role == UserRole.franchise_owner:
        account = db.get(FranchiseOwner, record.subject_id)
    if account is None or not account.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    access_token = create_access_token(subject_id=account.id, role=record.role)
    new_refresh = issue_refresh_token(db, record.role, account)
    return Token(access_token=access_token, refresh_token=new_refresh)


@router.get("/me", response_model=AuthMeResponse)
def get_me(
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    role, account = principal_to_account(db, current_user)
    return build_auth_me_response(role, account)


@router.patch("/me", response_model=AuthMeResponse)
def update_me(
    payload: MeUpdate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    role, account = principal_to_account(db, current_user)
    apply_me_update(account, role, payload)
    db.add(account)
    db.commit()
    db.refresh(account)
    return build_auth_me_response(role, account)


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    role, account = principal_to_account(db, current_user)
    if not verify_password(payload.current_password, account.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    account.hashed_password = hash_password(payload.new_password)
    db.add(account)
    db.commit()
    return MessageResponse(message="Password changed successfully")

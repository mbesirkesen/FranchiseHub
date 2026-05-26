from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Admin, Buyer, FranchiseOwner, UserRole
from ..schemas import (
    AdminCreate,
    AdminRead,
    BuyerCreate,
    BuyerRead,
    FranchiseOwnerCreate,
    FranchiseOwnerRead,
    Token,
    UserLogin,
)
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _email_exists(db: Session, email: str) -> bool:
    buyer_exists = db.scalar(select(Buyer.id).where(Buyer.email == email))
    owner_exists = db.scalar(select(FranchiseOwner.id).where(FranchiseOwner.email == email))
    admin_exists = db.scalar(select(Admin.id).where(Admin.email == email))
    return bool(buyer_exists or owner_exists or admin_exists)


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
    )
    db.add(user)
    db.commit()
    db.refresh(user)
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
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)
    return owner


@router.post("/register/admin", response_model=AdminRead, status_code=status.HTTP_201_CREATED)
def register_admin(payload: AdminCreate, db: Session = Depends(get_db)):
    if _email_exists(db, payload.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered",
        )

    admin = Admin(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        authorization_level=payload.authorization_level,
        is_superadmin=payload.is_superadmin,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


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

    account = db.scalar(select(Buyer).where(Buyer.email == payload.email))
    role = UserRole.buyer
    if account is None:
        account = db.scalar(select(FranchiseOwner).where(FranchiseOwner.email == payload.email))
        role = UserRole.franchise_owner
    if account is None:
        account = db.scalar(select(Admin).where(Admin.email == payload.email))
        role = UserRole.admin

    if not account or not verify_password(payload.password, account.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject_id=account.id, role=role)
    return Token(access_token=access_token)

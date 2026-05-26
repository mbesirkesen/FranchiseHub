from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_principal, require_roles
from ..models import Application, ApplicationStatus, Brand, UserRole
from ..schemas import (
    ApplicationRead,
    BrandCompareResponse,
    BrandCompareRequest,
    BrandRead,
    BuyerApplicationCreate,
    AuthenticatedPrincipal,
)

router = APIRouter(tags=["buyer"])


@router.get(
    "/brands",
    response_model=list[BrandRead],
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def list_brands(
    sector: Optional[str] = Query(default=None),
    min_cost: Optional[float] = Query(default=None, ge=0),
    max_cost: Optional[float] = Query(default=None, ge=0),
    location: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    stmt = select(Brand).where(Brand.is_approved.is_(True))
    if sector:
        stmt = stmt.where(Brand.sector.ilike(f"%{sector}%"))
    if min_cost is not None:
        stmt = stmt.where(Brand.initial_cost >= min_cost)
    if max_cost is not None:
        stmt = stmt.where(Brand.initial_cost <= max_cost)
    if location:
        stmt = stmt.where(Brand.location.ilike(f"%{location}%"))

    return db.scalars(stmt.order_by(Brand.initial_cost.asc())).all()


@router.get(
    "/brands/{brand_id}",
    response_model=BrandRead,
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def get_brand_detail(brand_id: int, db: Session = Depends(get_db)):
    brand = db.scalar(
        select(Brand).where(Brand.id == brand_id, Brand.is_approved.is_(True))
    )
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found",
        )
    return brand


@router.post(
    "/brands/compare",
    response_model=BrandCompareResponse,
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def compare_brands(payload: BrandCompareRequest, db: Session = Depends(get_db)):
    brands = db.scalars(
        select(Brand).where(Brand.id.in_(payload.brand_ids), Brand.is_approved.is_(True))
    ).all()
    if len(brands) != len(set(payload.brand_ids)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more brand IDs were not found",
        )
    return BrandCompareResponse(brands=brands)


@router.post(
    "/applications",
    response_model=ApplicationRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def create_application(
    payload: BuyerApplicationCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    brand = db.get(Brand, payload.brand_id)
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found",
        )
    if not brand.is_approved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Applications are only allowed for approved brands",
        )

    application = Application(
        buyer_id=current_user.user_id,
        brand_id=payload.brand_id,
        status=ApplicationStatus.pending,
        notes=payload.notes,
    )
    db.add(application)
    db.commit()
    db.refresh(application)
    return application

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Application, Brand
from ..reference_data import TR_CITIES
from ..schemas import PlatformStatsResponse, ReferenceListResponse

router = APIRouter(tags=["reference"])


@router.get("/reference/cities", response_model=ReferenceListResponse)
def list_cities():
    return ReferenceListResponse(items=list(TR_CITIES))


@router.get("/platform/stats", response_model=PlatformStatsResponse)
def platform_stats(db: Session = Depends(get_db)):
    approved_brands = int(
        db.scalar(select(func.count()).select_from(Brand).where(Brand.is_approved.is_(True))) or 0
    )
    total_applications = int(db.scalar(select(func.count()).select_from(Application)) or 0)
    sectors = db.scalars(
        select(Brand.sector)
        .where(Brand.is_approved.is_(True), Brand.sector.isnot(None), Brand.sector != "")
        .distinct()
        .order_by(Brand.sector.asc())
    ).all()
    return PlatformStatsResponse(
        approved_brands=approved_brands,
        total_applications=total_applications,
        sectors=[s.strip() for s in sectors if s and s.strip()],
    )

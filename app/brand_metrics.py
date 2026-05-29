from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .brand_service import get_approved_brand_or_404
from .models import (
    Application,
    ApplicationStatus,
    BrandFDDDocument,
    BrandMedia,
    BrandMediaType,
    BrandTerritory,
    FranchiseOutlet,
    TerritoryStatus,
)
from .schemas import BrandGrowthPoint, BrandMetricsResponse
from .security import utc_now


def _estimated_roi_percent(brand_id: int, initial_cost: float, approved_count: int) -> float:
    base = 12.0 + (brand_id % 11) * 0.9
    if initial_cost > 3_000_000:
        base -= 1.5
    base += min(approved_count * 0.8, 6.0)
    return round(min(max(base, 8.0), 32.0), 1)


def _growth_series(db: Session, brand_id: int) -> list[BrandGrowthPoint]:
    end = utc_now().replace(day=1)
    points: list[BrandGrowthPoint] = []
    for i in range(11, -1, -1):
        month_start = (end - timedelta(days=30 * i)).replace(day=1)
        month_key = month_start.strftime("%Y-%m")
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        count = int(
            db.scalar(
                select(func.count(Application.id)).where(
                    Application.brand_id == brand_id,
                    Application.created_at >= month_start,
                    Application.created_at < next_month,
                )
            )
            or 0
        )
        value = round(8.0 + (brand_id % 7) + count * 1.4 + (11 - i) * 0.3, 1)
        points.append(BrandGrowthPoint(month=month_key, value=value))
    return points


def build_brand_metrics(db: Session, brand_id: int) -> BrandMetricsResponse:
    brand = get_approved_brand_or_404(db, brand_id)

    applications_total = int(
        db.scalar(
            select(func.count(Application.id)).where(Application.brand_id == brand_id)
        )
        or 0
    )
    applications_approved = int(
        db.scalar(
            select(func.count(Application.id)).where(
                Application.brand_id == brand_id,
                Application.status == ApplicationStatus.approved,
            )
        )
        or 0
    )
    applications_pending = int(
        db.scalar(
            select(func.count(Application.id)).where(
                Application.brand_id == brand_id,
                Application.status == ApplicationStatus.pending,
            )
        )
        or 0
    )

    territories_available = int(
        db.scalar(
            select(func.count(BrandTerritory.id)).where(
                BrandTerritory.brand_id == brand_id,
                BrandTerritory.status == TerritoryStatus.available,
            )
        )
        or 0
    )
    territories_reserved = int(
        db.scalar(
            select(func.count(BrandTerritory.id)).where(
                BrandTerritory.brand_id == brand_id,
                BrandTerritory.status == TerritoryStatus.reserved,
            )
        )
        or 0
    )

    outlet_count = int(
        db.scalar(
            select(func.count(FranchiseOutlet.id)).where(
                FranchiseOutlet.brand_id == brand_id
            )
        )
        or 0
    )

    fdd_count = int(
        db.scalar(
            select(func.count(BrandFDDDocument.id)).where(
                BrandFDDDocument.brand_id == brand_id
            )
        )
        or 0
    )

    media_rows = db.scalars(
        select(BrandMedia).where(BrandMedia.brand_id == brand_id)
    ).all()
    has_logo = any(m.media_type == BrandMediaType.logo for m in media_rows)
    gallery_count = sum(1 for m in media_rows if m.media_type == BrandMediaType.gallery)

    initial_cost = float(brand.initial_cost)
    roi = _estimated_roi_percent(brand.id, initial_cost, applications_approved)

    return BrandMetricsResponse(
        brand_id=brand.id,
        brand_name=brand.name,
        applications_total=applications_total,
        applications_approved=applications_approved,
        applications_pending=applications_pending,
        territories_available=territories_available,
        territories_reserved=territories_reserved,
        territories_total=territories_available + territories_reserved,
        outlet_count=outlet_count,
        fdd_document_count=fdd_count,
        media_gallery_count=gallery_count,
        has_logo=has_logo,
        initial_cost=initial_cost,
        sector=brand.sector,
        location=brand.location,
        estimated_roi_percent=roi,
        growth_series=_growth_series(db, brand.id),
    )

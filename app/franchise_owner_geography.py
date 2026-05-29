from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Application, Brand, Buyer
from .schemas import FranchiseOwnerGeographyResponse, GeographyDemandPoint
from .security import utc_now


def build_geography_analytics(
    db: Session,
    *,
    franchise_owner_id: int,
    brand_id: Optional[int],
    days: int = 30,
) -> FranchiseOwnerGeographyResponse:
    if brand_id is None:
        return FranchiseOwnerGeographyResponse(period_days=days, points=[])

    since = utc_now() - timedelta(days=days)
    rows = db.execute(
        select(Application, Buyer)
        .join(Buyer, Application.buyer_id == Buyer.id)
        .where(
            Application.brand_id == brand_id,
            Application.created_at >= since,
        )
    ).all()

    by_city: dict[str, int] = defaultdict(int)
    for _app, buyer in rows:
        city = (buyer.city or "Bilinmiyor").strip()
        by_city[city] += 1

    if not by_city:
        brand = db.get(Brand, brand_id)
        if brand and brand.location:
            for part in brand.location.split(","):
                city = part.strip()
                if city:
                    by_city[city] = 1

    max_count = max(by_city.values()) if by_city else 1
    points = [
        GeographyDemandPoint(
            city=city,
            application_count=count,
            intensity=round(count / max_count, 3),
        )
        for city, count in sorted(by_city.items(), key=lambda x: -x[1])
    ]

    return FranchiseOwnerGeographyResponse(period_days=days, points=points)

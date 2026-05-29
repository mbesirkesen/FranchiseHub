from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Brand
from .schemas import BrandRead, RecommendedBrandItem


def score_brand_match(
    brand: Brand,
    *,
    investment_budget: float,
    preferred_sector: str,
    experience_years: int,
    city: Optional[str] = None,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    cost = float(brand.initial_cost)

    if cost <= investment_budget:
        score += 40
        reasons.append("Yatırım bütçenizin altında veya eşit")
    elif cost <= investment_budget * 1.15:
        score += 22
        reasons.append("Bütçenize yakın yatırım maliyeti")
    else:
        return 0, []

    sector_needle = preferred_sector.strip().lower()
    brand_sector = (brand.sector or "").lower()
    if sector_needle and brand_sector and sector_needle in brand_sector:
        score += 35
        reasons.append(f"Sektör uyumu: {brand.sector}")
    elif sector_needle and brand_sector:
        score += 10
        reasons.append("İlgili sektör ailesine yakın")

    if experience_years >= 5:
        score += 12
        reasons.append("Deneyiminize uygun franchise seviyesi")
    elif experience_years >= 2:
        score += 8
        reasons.append("Orta seviye deneyim için uygun")

    if city and brand.location and city.strip().lower() in brand.location.lower():
        score += 13
        reasons.append(f"Konum tercihi: {brand.location}")

    return min(score, 100), reasons


def recommend_brands(
    db: Session,
    *,
    investment_budget: float,
    preferred_sector: str,
    experience_years: int,
    city: Optional[str] = None,
    limit: int = 10,
) -> list[RecommendedBrandItem]:
    brands = db.scalars(select(Brand).where(Brand.is_approved.is_(True))).all()
    scored: list[RecommendedBrandItem] = []
    for brand in brands:
        match_score, match_reasons = score_brand_match(
            brand,
            investment_budget=investment_budget,
            preferred_sector=preferred_sector,
            experience_years=experience_years,
            city=city,
        )
        if match_score <= 0:
            continue
        scored.append(
            RecommendedBrandItem(
                brand=BrandRead.model_validate(brand),
                match_score=match_score,
                match_reasons=match_reasons,
            )
        )
    scored.sort(key=lambda x: (-x.match_score, x.brand.name))
    return scored[:limit]

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import Application, Brand, Buyer, UserRole
from .schemas import (
    AuthenticatedPrincipal,
    SearchApplicationHit,
    SearchBrandHit,
    SearchResponse,
)


def platform_search(
    db: Session,
    principal: AuthenticatedPrincipal,
    *,
    query: str,
    limit: int = 20,
) -> SearchResponse:
    term = query.strip()
    pattern = f"%{term}%"
    brand_limit = limit
    app_limit = limit

    brands: list[SearchBrandHit] = []
    applications: list[SearchApplicationHit] = []

    if principal.role == UserRole.buyer:
        brand_rows = db.scalars(
            select(Brand)
            .where(
                Brand.is_approved.is_(True),
                or_(
                    Brand.name.ilike(pattern),
                    Brand.sector.ilike(pattern),
                    Brand.location.ilike(pattern),
                ),
            )
            .order_by(Brand.name.asc())
            .limit(brand_limit)
        ).all()
        brands = [
            SearchBrandHit(
                id=b.id,
                name=b.name,
                sector=b.sector,
                location=b.location,
                is_approved=b.is_approved,
            )
            for b in brand_rows
        ]

        app_rows = db.execute(
            select(Application, Brand)
            .join(Brand, Application.brand_id == Brand.id)
            .where(
                Application.buyer_id == principal.user_id,
                or_(
                    Brand.name.ilike(pattern),
                    Application.notes.ilike(pattern),
                ),
            )
            .order_by(Application.created_at.desc())
            .limit(app_limit)
        ).all()
        applications = [
            SearchApplicationHit(
                id=app.id,
                status=app.status,
                brand_name=brand.name,
                notes=app.notes,
            )
            for app, brand in app_rows
        ]

    elif principal.role == UserRole.franchise_owner:
        brand_rows = db.scalars(
            select(Brand)
            .where(
                Brand.franchise_owner_id == principal.user_id,
                or_(
                    Brand.name.ilike(pattern),
                    Brand.sector.ilike(pattern),
                    Brand.location.ilike(pattern),
                ),
            )
            .order_by(Brand.name.asc())
            .limit(brand_limit)
        ).all()
        brands = [
            SearchBrandHit(
                id=b.id,
                name=b.name,
                sector=b.sector,
                location=b.location,
                is_approved=b.is_approved,
            )
            for b in brand_rows
        ]

        app_rows = db.execute(
            select(Application, Brand, Buyer)
            .join(Brand, Application.brand_id == Brand.id)
            .join(Buyer, Application.buyer_id == Buyer.id)
            .where(
                Brand.franchise_owner_id == principal.user_id,
                or_(
                    Buyer.email.ilike(pattern),
                    Buyer.first_name.ilike(pattern),
                    Buyer.last_name.ilike(pattern),
                    Application.notes.ilike(pattern),
                ),
            )
            .order_by(Application.created_at.desc())
            .limit(app_limit)
        ).all()
        applications = [
            SearchApplicationHit(
                id=app.id,
                status=app.status,
                buyer_email=buyer.email,
                buyer_name=f"{buyer.first_name} {buyer.last_name}".strip(),
                brand_name=brand.name,
                notes=app.notes,
            )
            for app, brand, buyer in app_rows
        ]

    return SearchResponse(query=term, brands=brands, applications=applications)

from __future__ import annotations

import math
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .file_tokens import build_media_public_url
from .region_filters import region_search_terms
from .models import (
    Brand,
    BrandFDDDocument,
    BrandMedia,
    BrandTerritory,
    TerritoryStatus,
)
from .schemas import (
    BrandCompareColumn,
    BrandCompareItem,
    BrandCompareResponse,
    BrandCompareRow,
    BrandCompareTable,
    BrandFDDRead,
    BrandFinancialSummary,
    BrandMediaListResponse,
    BrandMediaRead,
    BrandSort,
    BrandTerritoryListResponse,
    BrandTerritoryRead,
)


def get_approved_brand_or_404(db: Session, brand_id: int) -> Brand:
    brand = db.scalar(
        select(Brand).where(Brand.id == brand_id, Brand.is_approved.is_(True))
    )
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found",
        )
    return brand


def apply_brand_filters(
    stmt,
    *,
    sector: Optional[str],
    min_cost: Optional[float],
    max_cost: Optional[float],
    location: Optional[str],
    region: Optional[str],
    q: Optional[str],
):
    if sector:
        stmt = stmt.where(Brand.sector.ilike(f"%{sector}%"))
    if min_cost is not None:
        stmt = stmt.where(Brand.initial_cost >= min_cost)
    if max_cost is not None:
        stmt = stmt.where(Brand.initial_cost <= max_cost)
    if location:
        stmt = stmt.where(Brand.location.ilike(f"%{location}%"))
    if region:
        terms = region_search_terms(region)
        region_clauses = []
        for term in terms:
            pattern = f"%{term}%"
            territory_ids = (
                select(BrandTerritory.brand_id)
                .where(
                    or_(
                        BrandTerritory.region_code.ilike(pattern),
                        BrandTerritory.name.ilike(pattern),
                    )
                )
                .distinct()
            )
            region_clauses.append(Brand.location.ilike(pattern))
            region_clauses.append(Brand.id.in_(territory_ids))
        stmt = stmt.where(or_(*region_clauses))
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Brand.name.ilike(pattern),
                Brand.sector.ilike(pattern),
                Brand.location.ilike(pattern),
                Brand.description.ilike(pattern),
            )
        )
    return stmt


def apply_brand_sort(stmt, sort: BrandSort):
    if sort == BrandSort.name_asc:
        return stmt.order_by(Brand.name.asc())
    if sort == BrandSort.name_desc:
        return stmt.order_by(Brand.name.desc())
    if sort == BrandSort.cost_desc:
        return stmt.order_by(Brand.initial_cost.desc())
    return stmt.order_by(Brand.initial_cost.asc())


def list_approved_brands(
    db: Session,
    *,
    sector: Optional[str],
    min_cost: Optional[float],
    max_cost: Optional[float],
    location: Optional[str],
    region: Optional[str],
    q: Optional[str],
    page: int,
    page_size: int,
    sort: BrandSort,
) -> tuple[list[Brand], int]:
    base = select(Brand).where(Brand.is_approved.is_(True))
    base = apply_brand_filters(
        base,
        sector=sector,
        min_cost=min_cost,
        max_cost=max_cost,
        location=location,
        region=region,
        q=q,
    )
    count_stmt = select(func.count()).select_from(base.subquery())
    total = int(db.scalar(count_stmt) or 0)
    stmt = apply_brand_sort(base, sort)
    offset = (page - 1) * page_size
    items = db.scalars(stmt.offset(offset).limit(page_size)).all()
    return items, total


def total_pages(total: int, page_size: int) -> int:
    if total == 0:
        return 0
    return math.ceil(total / page_size)


_COMPARE_FIELDS: list[tuple[str, str, str]] = [
    ("name", "Marka adı", "name"),
    ("sector", "Sektör", "sector"),
    ("location", "Konum", "location"),
    ("initial_cost", "Yatırım maliyeti", "initial_cost"),
    ("support_details", "Destek", "support_details"),
    ("description", "Açıklama", "description"),
]


def build_compare_response(brands: list[Brand]) -> BrandCompareResponse:
    ordered = sorted(brands, key=lambda b: b.id)
    items = [BrandCompareItem.model_validate(b) for b in ordered]
    columns = [BrandCompareColumn(brand_id=b.id, name=b.name) for b in ordered]
    rows: list[BrandCompareRow] = []
    for key, label, attr in _COMPARE_FIELDS:
        values: list[Optional[str]] = []
        for brand in ordered:
            raw = getattr(brand, attr, None)
            if raw is None:
                values.append(None)
            elif attr == "initial_cost":
                values.append(f"{float(raw):,.0f}")
            else:
                values.append(str(raw))
        rows.append(BrandCompareRow(key=key, label=label, values=values))
    financial_summaries = [
        BrandFinancialSummary(
            brand_id=b.id,
            name=b.name,
            initial_cost=float(b.initial_cost),
            min_investment_cost=float(b.initial_cost),
            max_investment_cost=float(b.initial_cost),
            sector=b.sector,
            location=b.location,
            support_details=b.support_details,
        )
        for b in ordered
    ]
    return BrandCompareResponse(
        brands=items,
        comparison_table=BrandCompareTable(columns=columns, rows=rows),
        financial_summaries=financial_summaries,
    )


def media_to_read(media: BrandMedia) -> BrandMediaRead:
    return BrandMediaRead(
        id=media.id,
        brand_id=media.brand_id,
        media_type=media.media_type.value,
        url=build_media_public_url(media.id),
        mime_type=media.mime_type,
        original_filename=media.original_filename,
        sort_order=media.sort_order,
    )


def build_media_list(db: Session, brand_id: int) -> BrandMediaListResponse:
    rows = db.scalars(
        select(BrandMedia)
        .where(BrandMedia.brand_id == brand_id)
        .order_by(BrandMedia.sort_order.asc(), BrandMedia.id.asc())
    ).all()
    logo = None
    gallery: list[BrandMediaRead] = []
    for row in rows:
        item = media_to_read(row)
        if row.media_type.value == "logo":
            logo = item
        else:
            gallery.append(item)
    return BrandMediaListResponse(logo=logo, gallery=gallery)


def build_territory_list(db: Session, brand_id: int) -> BrandTerritoryListResponse:
    rows = db.scalars(
        select(BrandTerritory)
        .where(BrandTerritory.brand_id == brand_id)
        .order_by(BrandTerritory.name.asc())
    ).all()
    items = [BrandTerritoryRead.model_validate(r) for r in rows]
    available = sum(1 for r in rows if r.status == TerritoryStatus.available)
    reserved = sum(1 for r in rows if r.status == TerritoryStatus.reserved)
    return BrandTerritoryListResponse(
        items=items,
        available_count=available,
        reserved_count=reserved,
    )


def list_fdd_metadata(db: Session, brand_id: int) -> list[BrandFDDRead]:
    rows = db.scalars(
        select(BrandFDDDocument)
        .where(BrandFDDDocument.brand_id == brand_id)
        .order_by(BrandFDDDocument.published_at.desc().nullslast(), BrandFDDDocument.id.desc())
    ).all()
    return [BrandFDDRead.model_validate(r) for r in rows]

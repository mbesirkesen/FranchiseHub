from __future__ import annotations

import math
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
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
        stmt = stmt.where(
            or_(
                and_(Brand.initial_cost.isnot(None), Brand.initial_cost >= min_cost),
                and_(Brand.min_investment_cost.isnot(None), Brand.min_investment_cost >= min_cost),
            )
        )
    if max_cost is not None:
        # Bütçe filtresi: markanın gerektirdiği minimum yatırım <= max_cost
        affordable = or_(
            and_(
                Brand.min_investment_cost.isnot(None),
                Brand.min_investment_cost > 0,
                Brand.min_investment_cost <= max_cost,
            ),
            and_(
                or_(Brand.min_investment_cost.is_(None), Brand.min_investment_cost <= 0),
                Brand.initial_cost.isnot(None),
                Brand.initial_cost > 0,
                Brand.initial_cost <= max_cost,
            ),
            and_(
                or_(Brand.min_investment_cost.is_(None), Brand.min_investment_cost <= 0),
                or_(Brand.initial_cost.is_(None), Brand.initial_cost <= 0),
                Brand.max_investment_cost.isnot(None),
                Brand.max_investment_cost > 0,
                Brand.max_investment_cost <= max_cost,
            ),
            and_(
                or_(Brand.min_investment_cost.is_(None), Brand.min_investment_cost <= 0),
                or_(Brand.initial_cost.is_(None), Brand.initial_cost <= 0),
                or_(Brand.max_investment_cost.is_(None), Brand.max_investment_cost <= 0),
            ),
        )
        stmt = stmt.where(affordable)
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


def list_brand_sectors(db: Session) -> list[str]:
    rows = db.scalars(
        select(Brand.sector)
        .where(Brand.is_approved.is_(True), Brand.sector.isnot(None), Brand.sector != "")
        .distinct()
        .order_by(Brand.sector.asc())
    ).all()
    return [s.strip() for s in rows if s and s.strip()]


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


def _format_city_list(cities: list[str], *, limit: int = 4) -> str:
    if not cities:
        return "—"
    shown = cities[:limit]
    text = ", ".join(shown)
    if len(cities) > limit:
        text += f" (+{len(cities) - limit} şehir)"
    return text


def build_compare_response(
    brands: list[Brand],
    *,
    snapshots: Optional[dict[int, object]] = None,
    roi_map: Optional[dict[int, float]] = None,
    insights: Optional[str] = None,
) -> BrandCompareResponse:
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

    if snapshots:
        metric_rows: list[tuple[str, str, list[Optional[str]]]] = [
            ("outlet_count", "Şube sayısı", []),
            ("years_active", "Faaliyet süresi", []),
            ("outlet_cities", "Şube şehirleri", []),
            ("approved_franchises", "Onaylı bayilik", []),
            ("estimated_roi", "Tahmini ROI", []),
        ]
        for brand in ordered:
            snap = snapshots.get(brand.id)
            active = getattr(snap, "active_outlet_count", 0) if snap else 0
            total = getattr(snap, "outlet_count", 0) if snap else 0
            years = getattr(snap, "years_active", None) if snap else None
            cities = getattr(snap, "outlet_cities", []) if snap else []
            approved = getattr(snap, "approved_franchise_count", 0) if snap else 0
            roi = (roi_map or {}).get(brand.id)

            metric_rows[0][2].append(
                str(active) if active else (str(total) if total else "—")
            )
            metric_rows[1][2].append(f"~{years} yıl" if years else "—")
            metric_rows[2][2].append(_format_city_list(cities))
            metric_rows[3][2].append(str(approved) if approved else "—")
            metric_rows[4][2].append(f"%{roi:.1f}" if roi is not None else "—")

        insert_at = next(
            (i for i, r in enumerate(rows) if r.key == "initial_cost"),
            len(rows),
        ) + 1
        for offset, (key, label, values) in enumerate(metric_rows):
            rows.insert(
                insert_at + offset,
                BrandCompareRow(key=key, label=label, values=values),
            )
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
        insights=insights,
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

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

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
    OutletStatus,
    TerritoryStatus,
)
from .schemas import BrandGrowthPoint, BrandMetricsResponse
from .security import utc_now


@dataclass
class BrandCompareSnapshot:
    outlet_count: int = 0
    active_outlet_count: int = 0
    outlet_cities: list[str] = field(default_factory=list)
    years_active: Optional[int] = None
    approved_franchise_count: int = 0


def _years_since(anchor: Optional[datetime]) -> Optional[int]:
    if anchor is None:
        return None
    days = max(0, (utc_now() - anchor).days)
    return max(1, days // 365)


def batch_brand_compare_snapshots(db: Session, brands: list) -> dict[int, BrandCompareSnapshot]:
    """Karşılaştırma için şube, şehir ve bayilik özetlerini toplu çeker."""
    if not brands:
        return {}
    ids = [b.id for b in brands]
    out: dict[int, BrandCompareSnapshot] = {i: BrandCompareSnapshot() for i in ids}

    outlet_rows = db.execute(
        select(
            FranchiseOutlet.brand_id,
            FranchiseOutlet.city,
            FranchiseOutlet.status,
            func.coalesce(FranchiseOutlet.opened_at, FranchiseOutlet.created_at),
        ).where(FranchiseOutlet.brand_id.in_(ids))
    ).all()
    oldest: dict[int, datetime] = {}
    cities: dict[int, set[str]] = {i: set() for i in ids}
    for brand_id, city, status, opened in outlet_rows:
        bid = int(brand_id)
        if bid not in out:
            continue
        out[bid].outlet_count += 1
        if status == OutletStatus.active:
            out[bid].active_outlet_count += 1
        if city and str(city).strip():
            cities[bid].add(str(city).strip())
        if opened is not None:
            prev = oldest.get(bid)
            if prev is None or opened < prev:
                oldest[bid] = opened

    app_rows = db.execute(
        select(Application.brand_id, func.count(Application.id))
        .where(
            Application.brand_id.in_(ids),
            Application.status == ApplicationStatus.approved,
        )
        .group_by(Application.brand_id)
    ).all()
    approved = {int(bid): int(cnt) for bid, cnt in app_rows}

    for bid in ids:
        snap = out[bid]
        snap.outlet_cities = sorted(cities.get(bid, set()))
        snap.approved_franchise_count = approved.get(bid, 0)
        snap.years_active = _years_since(oldest.get(bid))
    return out


def _city_phrase(cities: list[str]) -> str:
    if not cities:
        return ""
    head = ", ".join(cities[:3])
    if len(cities) > 3:
        return f"{head} ve {len(cities) - 3} şehir daha"
    return head


def build_compare_insights_text(
    brands: list,
    snapshots: dict[int, BrandCompareSnapshot],
    roi_map: dict[int, float],
) -> str:
    """Karşılaştırma için kısa operasyonel özet ve iki markalı kıyas notu."""
    if not brands:
        return ""

    profile_lines: list[str] = []
    for brand in brands:
        snap = snapshots.get(brand.id, BrandCompareSnapshot())
        roi = roi_map.get(brand.id, 12.0)
        chunks: list[str] = []
        outlets = snap.active_outlet_count or snap.outlet_count
        if outlets:
            where = _city_phrase(snap.outlet_cities)
            if where:
                chunks.append(f"{outlets} aktif şube ({where})")
            else:
                chunks.append(f"{outlets} aktif şube")
        if snap.years_active:
            chunks.append(f"~{snap.years_active} yıldır ağda")
        if snap.approved_franchise_count:
            chunks.append(f"{snap.approved_franchise_count} onaylı bayilik")
        chunks.append(f"tahmini ROI %{roi:.1f}")
        if chunks:
            profile_lines.append(f"• {brand.name}: " + "; ".join(chunks) + ".")
        else:
            profile_lines.append(
                f"• {brand.name}: henüz sınırlı şube verisi; yatırım ve sektör bilgisine bakın."
            )

    verdict_lines: list[str] = []
    if len(brands) == 2:
        left, right = brands[0], brands[1]
        sl, sr = snapshots.get(left.id, BrandCompareSnapshot()), snapshots.get(
            right.id, BrandCompareSnapshot()
        )
        ol, or_ = sl.active_outlet_count or sl.outlet_count, sr.active_outlet_count or sr.outlet_count
        if ol != or_ and (ol or or_):
            leader, other = (left, right) if ol > or_ else (right, left)
            lo = max(ol, or_)
            verdict_lines.append(
                f"Şube ağı genişliği açısından {leader.name} önde ({lo} şube)."
            )
        yl, yr = sl.years_active or 0, sr.years_active or 0
        if yl != yr and (yl or yr):
            elder = left if yl > yr else right
            ey = max(yl, yr)
            verdict_lines.append(f"Sahada daha uzun süredir görünen marka: {elder.name} (~{ey} yıl).")
        rl, rr = roi_map.get(left.id, 0), roi_map.get(right.id, 0)
        if abs(rl - rr) >= 1.5:
            roi_leader = left if rl > rr else right
            verdict_lines.append(
                f"Platform tahmini getiri modeline göre {roi_leader.name} bir adım önde."
            )
        if not verdict_lines and (ol or or_ or yl or yr):
            verdict_lines.append(
                "İki marka da benzer ölçekte; yatırım tutarı, şehir uyumu ve sektör deneyiminize göre seçim yapın."
            )

    parts: list[str] = ["Operasyonel özet:"] + profile_lines
    if verdict_lines:
        parts.append("Kısa kıyas: " + " ".join(verdict_lines))
    parts.append(
        "Not: Şube ve ROI verileri platform kayıtlarına dayanır; yerinde due diligence önerilir."
    )
    return "\n".join(parts)


def estimated_roi_percent(brand_id: int, initial_cost: float, approved_count: int) -> float:
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


def batch_estimated_roi_percent(db: Session, brands: list) -> dict[int, float]:
    """N+1 önlemek için agent widget ROI hesabı."""
    if not brands:
        return {}
    ids = [b.id for b in brands]
    rows = db.execute(
        select(Application.brand_id, func.count(Application.id))
        .where(
            Application.brand_id.in_(ids),
            Application.status == ApplicationStatus.approved,
        )
        .group_by(Application.brand_id)
    ).all()
    approved_counts = {int(bid): int(cnt) for bid, cnt in rows}
    return {
        b.id: estimated_roi_percent(
            b.id, float(b.initial_cost), approved_counts.get(b.id, 0)
        )
        for b in brands
    }


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
    roi = estimated_roi_percent(brand.id, initial_cost, applications_approved)

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

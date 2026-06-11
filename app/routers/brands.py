from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..brand_metrics import (
    batch_brand_compare_snapshots,
    batch_estimated_roi_percent,
    build_brand_metrics,
    build_compare_insights_text,
)
from ..brand_service import (
    build_compare_response,
    build_media_list,
    build_territory_list,
    get_approved_brand_or_404,
    list_approved_brands,
    list_brand_sectors,
    list_fdd_metadata,
    total_pages,
)
from ..database import get_db
from ..file_tokens import (
    DOWNLOAD_TOKEN_EXPIRE_MINUTES,
    build_fdd_download_url,
    create_fdd_download_token,
)
from ..models import Brand, BrandFDDDocument
from ..region_filters import REGION_ALIASES, REGION_LABELS
from ..schemas import (
    BrandCompareRequest,
    BrandCompareResponse,
    BrandFDDDownloadResponse,
    BrandFDDListResponse,
    BrandListPage,
    BrandMediaListResponse,
    BrandMetricsResponse,
    BrandRead,
    BrandSort,
    BrandTerritoryListResponse,
    RegionListResponse,
    RegionOption,
    SectorListResponse,
)

router = APIRouter(tags=["brands-discovery"])


@router.get("/regions", response_model=RegionListResponse)
def list_regions():
    return RegionListResponse(
        items=[
            RegionOption(key=key, label=REGION_LABELS.get(key, key.title()))
            for key in REGION_ALIASES.keys()
        ]
    )


@router.get("/brands/sectors", response_model=SectorListResponse)
def list_sectors(db: Session = Depends(get_db)):
    return SectorListResponse(items=list_brand_sectors(db))


@router.get("/brands", response_model=BrandListPage)
def list_brands(
    sector: Optional[str] = Query(default=None),
    min_cost: Optional[float] = Query(default=None, ge=0),
    max_cost: Optional[float] = Query(default=None, ge=0),
    location: Optional[str] = Query(default=None),
    region: Optional[str] = Query(
        default=None,
        description="Filter by territory region_code/name or brand location",
    ),
    q: Optional[str] = Query(default=None, description="Search name, sector, location, description"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: BrandSort = Query(default=BrandSort.cost_asc),
    db: Session = Depends(get_db),
):
    items, total = list_approved_brands(
        db,
        sector=sector,
        min_cost=min_cost,
        max_cost=max_cost,
        location=location,
        region=region,
        q=q,
        page=page,
        page_size=page_size,
        sort=sort,
    )
    return BrandListPage(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages(total, page_size),
    )


@router.get("/brands/{brand_id}", response_model=BrandRead)
def get_brand_detail(brand_id: int, db: Session = Depends(get_db)):
    return get_approved_brand_or_404(db, brand_id)


@router.get("/brands/{brand_id}/metrics", response_model=BrandMetricsResponse)
def get_brand_metrics(brand_id: int, db: Session = Depends(get_db)):
    return build_brand_metrics(db, brand_id)


@router.post("/brands/compare", response_model=BrandCompareResponse)
def compare_brands(payload: BrandCompareRequest, db: Session = Depends(get_db)):
    brands = db.scalars(
        select(Brand).where(Brand.id.in_(payload.brand_ids), Brand.is_approved.is_(True))
    ).all()
    if len(brands) != len(set(payload.brand_ids)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more brand IDs were not found",
        )
    snapshots = batch_brand_compare_snapshots(db, brands)
    roi_map = batch_estimated_roi_percent(db, brands)
    insights = build_compare_insights_text(brands, snapshots, roi_map)
    return build_compare_response(
        brands, snapshots=snapshots, roi_map=roi_map, insights=insights
    )


@router.get("/brands/{brand_id}/media", response_model=BrandMediaListResponse)
def get_brand_media(brand_id: int, db: Session = Depends(get_db)):
    get_approved_brand_or_404(db, brand_id)
    return build_media_list(db, brand_id)


@router.get("/brands/{brand_id}/fdd", response_model=BrandFDDListResponse)
def list_brand_fdd(brand_id: int, db: Session = Depends(get_db)):
    get_approved_brand_or_404(db, brand_id)
    return BrandFDDListResponse(items=list_fdd_metadata(db, brand_id))


@router.get("/brands/{brand_id}/fdd/{fdd_id}/download", response_model=BrandFDDDownloadResponse)
def get_fdd_download_url(brand_id: int, fdd_id: int, db: Session = Depends(get_db)):
    get_approved_brand_or_404(db, brand_id)
    doc = db.scalar(
        select(BrandFDDDocument).where(
            BrandFDDDocument.id == fdd_id,
            BrandFDDDocument.brand_id == brand_id,
        )
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="FDD document not found",
        )
    token, expires_at = create_fdd_download_token(brand_id=brand_id, fdd_id=fdd_id)
    return BrandFDDDownloadResponse(
        download_url=build_fdd_download_url(brand_id=brand_id, fdd_id=fdd_id, token=token),
        expires_at=expires_at,
        expires_in_seconds=DOWNLOAD_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/brands/{brand_id}/territories", response_model=BrandTerritoryListResponse)
def list_brand_territories(brand_id: int, db: Session = Depends(get_db)):
    get_approved_brand_or_404(db, brand_id)
    return build_territory_list(db, brand_id)

from __future__ import annotations

from typing import Optional

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..brand_service import media_to_read
from ..database import get_db
from ..dependencies import get_current_principal, require_roles
from ..models import (
    Application,
    ApplicationStatus,
    Brand,
    BrandFDDDocument,
    BrandMedia,
    BrandMediaType,
    Inventory,
    SupplyRequest,
    SupplyRequestStatus,
    UserRole,
)
from ..schemas import (
    ApplicationListEnvelope,
    ApplicationRead,
    ApplicationUpdate,
    AuthenticatedPrincipal,
    BrandFDDRead,
    BrandFDDUploadResponse,
    BrandMediaUploadResponse,
    BrandRead,
    FranchiseOwnerBrandWrite,
    FranchiseOwnerDashboardSummary,
)
from ..pagination import paginated_meta
from ..storage import ALLOWED_IMAGE_TYPES, ALLOWED_PDF_TYPES, save_upload_file

router = APIRouter(tags=["franchise-owner"])


def get_owned_brand_optional(
    db: Session, current_user: AuthenticatedPrincipal
) -> Brand | None:
    return db.scalar(
        select(Brand).where(Brand.franchise_owner_id == current_user.user_id)
    )


def get_owned_brand_or_404(db: Session, current_user: AuthenticatedPrincipal) -> Brand:
    brand = get_owned_brand_optional(db, current_user)
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No brand is assigned to this franchise owner",
        )
    return brand


def get_application_for_brand_or_404(
    db: Session,
    current_user: AuthenticatedPrincipal,
    application_id: int,
) -> Application:
    brand = get_owned_brand_or_404(db, current_user)
    application = db.get(Application, application_id)
    if not application or application.brand_id != brand.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found for your brand",
        )
    return application


@router.get(
    "/franchise-owner/dashboard/summary",
    response_model=FranchiseOwnerDashboardSummary,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def franchise_owner_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    brand = get_owned_brand_optional(db, current_user)
    if brand is None:
        inv_count = db.scalar(
            select(func.count(Inventory.id)).where(
                Inventory.franchise_owner_id == current_user.user_id
            )
        )
        sr_pending = db.scalar(
            select(func.count(SupplyRequest.id)).where(
                SupplyRequest.franchise_owner_id == current_user.user_id,
                SupplyRequest.status == SupplyRequestStatus.pending,
            )
        )
        sr_total = db.scalar(
            select(func.count(SupplyRequest.id)).where(
                SupplyRequest.franchise_owner_id == current_user.user_id
            )
        )
        return FranchiseOwnerDashboardSummary(
            has_brand=False,
            inventory_item_count=int(inv_count or 0),
            supply_requests_pending=int(sr_pending or 0),
            supply_requests_total=int(sr_total or 0),
        )

    pending = db.scalar(
        select(func.count(Application.id)).where(
            Application.brand_id == brand.id,
            Application.status == ApplicationStatus.pending,
        )
    )
    approved = db.scalar(
        select(func.count(Application.id)).where(
            Application.brand_id == brand.id,
            Application.status == ApplicationStatus.approved,
        )
    )
    rejected = db.scalar(
        select(func.count(Application.id)).where(
            Application.brand_id == brand.id,
            Application.status == ApplicationStatus.rejected,
        )
    )
    total = db.scalar(
        select(func.count(Application.id)).where(Application.brand_id == brand.id)
    )
    inv_count = db.scalar(
        select(func.count(Inventory.id)).where(
            Inventory.franchise_owner_id == current_user.user_id
        )
    )
    sr_pending = db.scalar(
        select(func.count(SupplyRequest.id)).where(
            SupplyRequest.franchise_owner_id == current_user.user_id,
            SupplyRequest.status == SupplyRequestStatus.pending,
        )
    )
    sr_total = db.scalar(
        select(func.count(SupplyRequest.id)).where(
            SupplyRequest.franchise_owner_id == current_user.user_id
        )
    )

    return FranchiseOwnerDashboardSummary(
        has_brand=True,
        brand_id=brand.id,
        brand_name=brand.name,
        applications_pending=int(pending or 0),
        applications_approved=int(approved or 0),
        applications_rejected=int(rejected or 0),
        applications_total=int(total or 0),
        inventory_item_count=int(inv_count or 0),
        supply_requests_pending=int(sr_pending or 0),
        supply_requests_total=int(sr_total or 0),
    )


@router.get(
    "/franchise-owner/my-brand",
    response_model=Optional[BrandRead],
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def get_my_brand(
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    return get_owned_brand_optional(db, current_user)


@router.post(
    "/franchise-owner/brand",
    response_model=BrandRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def create_my_brand(
    payload: FranchiseOwnerBrandWrite,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    if get_owned_brand_optional(db, current_user) is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This franchise owner already has a brand",
        )
    if not payload.name or not str(payload.name).strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="name is required",
        )
    try:
        initial = payload.resolved_initial_cost()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    brand = Brand(
        franchise_owner_id=current_user.user_id,
        name=payload.name.strip(),
        sector=payload.sector,
        description=payload.description,
        initial_cost=initial,
        support_details=payload.support_details,
        location=payload.location,
        is_approved=False,
    )
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


@router.patch(
    "/franchise-owner/brand",
    response_model=BrandRead,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def update_my_brand(
    payload: FranchiseOwnerBrandWrite,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    brand = get_owned_brand_optional(db, current_user)
    if brand is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No brand to update",
        )
    if payload.name is not None and str(payload.name).strip():
        brand.name = payload.name.strip()
    if payload.sector is not None:
        brand.sector = payload.sector
    if payload.location is not None:
        brand.location = payload.location
    if payload.description is not None:
        brand.description = payload.description
    if payload.support_details is not None:
        brand.support_details = payload.support_details
    cost_fields = (
        payload.initial_cost is not None
        or payload.min_investment_cost is not None
        or payload.max_investment_cost is not None
    )
    if cost_fields:
        try:
            brand.initial_cost = payload.resolved_initial_cost()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
    db.commit()
    db.refresh(brand)
    return brand


@router.post(
    "/franchise-owner/brand/media",
    response_model=BrandMediaUploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
async def upload_brand_media(
    file: UploadFile = File(...),
    media_type: BrandMediaType = Form(...),
    sort_order: int = Form(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    brand = get_owned_brand_or_404(db, current_user)
    relative_path, mime_type, _size = save_upload_file(
        file,
        subdir=f"brands/{brand.id}/media",
        allowed_mime=ALLOWED_IMAGE_TYPES,
    )
    if media_type == BrandMediaType.logo:
        db.execute(
            delete(BrandMedia).where(
                BrandMedia.brand_id == brand.id,
                BrandMedia.media_type == BrandMediaType.logo,
            )
        )
    media = BrandMedia(
        brand_id=brand.id,
        media_type=media_type,
        file_path=relative_path,
        mime_type=mime_type,
        original_filename=file.filename,
        sort_order=sort_order,
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return BrandMediaUploadResponse(media=media_to_read(media))


@router.post(
    "/franchise-owner/brand/fdd",
    response_model=BrandFDDUploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
async def upload_brand_fdd(
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=255),
    version: Optional[str] = Form(default=None, max_length=64),
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    brand = get_owned_brand_or_404(db, current_user)
    relative_path, mime_type, size = save_upload_file(
        file,
        subdir=f"brands/{brand.id}/fdd",
        allowed_mime=ALLOWED_PDF_TYPES,
    )
    doc = BrandFDDDocument(
        brand_id=brand.id,
        title=title.strip(),
        version=version.strip() if version else None,
        file_path=relative_path,
        mime_type=mime_type,
        file_size_bytes=size,
        published_at=datetime.utcnow(),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return BrandFDDUploadResponse(document=BrandFDDRead.model_validate(doc))


@router.get(
    "/applications/my-brand",
    response_model=ApplicationListEnvelope,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def list_my_brand_applications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    brand = get_owned_brand_optional(db, current_user)
    if brand is None:
        meta = paginated_meta(0, page, page_size)
        return ApplicationListEnvelope(items=[], **meta)
    stmt = (
        select(Application)
        .where(Application.brand_id == brand.id)
        .order_by(Application.created_at.desc(), Application.id.desc())
    )
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    offset = (page - 1) * page_size
    rows = db.scalars(stmt.offset(offset).limit(page_size)).all()
    meta = paginated_meta(total, page, page_size)
    return ApplicationListEnvelope(items=list(rows), **meta)


@router.patch(
    "/applications/{application_id}",
    response_model=ApplicationRead,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def update_application_status(
    application_id: int,
    payload: ApplicationUpdate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    application = get_application_for_brand_or_404(db, current_user, application_id)
    if payload.status not in {ApplicationStatus.approved, ApplicationStatus.rejected}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status can only be approved or rejected",
        )

    application.status = payload.status
    if payload.notes is not None:
        application.notes = payload.notes
    db.commit()
    db.refresh(application)
    return application


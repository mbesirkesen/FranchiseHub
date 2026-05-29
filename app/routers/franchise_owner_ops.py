from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_principal, require_roles
from ..file_tokens import build_owner_document_url
from ..franchise_owner_analytics import build_owner_analytics
from ..franchise_owner_ecosystem import build_franchise_owner_ecosystem
from ..franchise_owner_geography import build_geography_analytics
from ..franchise_owner_territories import (
    create_owner_territory,
    delete_owner_territory,
    list_owner_territories,
    update_owner_territory,
)
from ..models import (
    FranchiseOutlet,
    FranchiseOwnerDocument,
    OutletStatus,
    OwnerDocumentType,
    UserRole,
)
from ..routers.franchise_owner import get_owned_brand_optional
from ..pagination import paginated_meta
from ..schemas import (
    AuthenticatedPrincipal,
    FranchiseOutletCreate,
    FranchiseOutletListResponse,
    FranchiseOutletRead,
    FranchiseOutletUpdate,
    FranchiseOwnerAnalyticsResponse,
    FranchiseOwnerEcosystemResponse,
    FranchiseOwnerGeographyResponse,
    FranchiseOwnerDocumentListResponse,
    BrandTerritoryCreate,
    BrandTerritoryListResponse,
    BrandTerritoryRead,
    BrandTerritoryUpdate,
    FranchiseOwnerDocumentRead,
    FranchiseOwnerDocumentUploadResponse,
    OwnerDocumentType as OwnerDocumentTypeSchema,
)
from ..storage import ALLOWED_DOCUMENT_TYPES, save_upload_file

router = APIRouter(tags=["franchise-owner"])


def _outlet_for_owner_or_404(
    db: Session, current_user: AuthenticatedPrincipal, outlet_id: int
) -> FranchiseOutlet:
    outlet = db.scalar(
        select(FranchiseOutlet).where(
            FranchiseOutlet.id == outlet_id,
            FranchiseOutlet.franchise_owner_id == current_user.user_id,
        )
    )
    if not outlet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outlet not found",
        )
    return outlet


def _document_to_read(doc: FranchiseOwnerDocument) -> FranchiseOwnerDocumentRead:
    return FranchiseOwnerDocumentRead(
        id=doc.id,
        franchise_owner_id=doc.franchise_owner_id,
        title=doc.title,
        document_type=OwnerDocumentTypeSchema(doc.document_type.value),
        mime_type=doc.mime_type,
        file_size_bytes=doc.file_size_bytes,
        original_filename=doc.original_filename,
        download_url=build_owner_document_url(doc.id),
        created_at=doc.created_at,
    )


@router.get(
    "/franchise-owner/outlets",
    response_model=FranchiseOutletListResponse,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def list_outlets(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    stmt = (
        select(FranchiseOutlet)
        .where(FranchiseOutlet.franchise_owner_id == current_user.user_id)
        .order_by(FranchiseOutlet.created_at.desc(), FranchiseOutlet.id.desc())
    )
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    offset = (page - 1) * page_size
    rows = db.scalars(stmt.offset(offset).limit(page_size)).all()
    meta = paginated_meta(total, page, page_size)
    return FranchiseOutletListResponse(items=list(rows), **meta)


@router.post(
    "/franchise-owner/outlets",
    response_model=FranchiseOutletRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def create_outlet(
    payload: FranchiseOutletCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    brand = get_owned_brand_optional(db, current_user)
    outlet = FranchiseOutlet(
        franchise_owner_id=current_user.user_id,
        brand_id=brand.id if brand else None,
        name=payload.name.strip(),
        city=payload.city.strip(),
        address=payload.address,
        status=OutletStatus(payload.status.value),
        opened_at=payload.opened_at,
    )
    db.add(outlet)
    db.commit()
    db.refresh(outlet)
    return outlet


@router.patch(
    "/franchise-owner/outlets/{outlet_id}",
    response_model=FranchiseOutletRead,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def update_outlet(
    outlet_id: int,
    payload: FranchiseOutletUpdate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    outlet = _outlet_for_owner_or_404(db, current_user, outlet_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key == "name" and value is not None:
            value = str(value).strip()
        elif key == "city" and value is not None:
            value = str(value).strip()
        elif key == "status" and value is not None:
            value = OutletStatus(value.value)
        setattr(outlet, key, value)
    db.add(outlet)
    db.commit()
    db.refresh(outlet)
    return outlet


@router.delete(
    "/franchise-owner/outlets/{outlet_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def delete_outlet(
    outlet_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    outlet = _outlet_for_owner_or_404(db, current_user, outlet_id)
    db.delete(outlet)
    db.commit()


@router.get(
    "/franchise-owner/documents",
    response_model=FranchiseOwnerDocumentListResponse,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def list_documents(
    document_type: Optional[OwnerDocumentTypeSchema] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    stmt = select(FranchiseOwnerDocument).where(
        FranchiseOwnerDocument.franchise_owner_id == current_user.user_id
    )
    if document_type is not None:
        stmt = stmt.where(
            FranchiseOwnerDocument.document_type == OwnerDocumentType(document_type.value)
        )
    stmt = stmt.order_by(
        FranchiseOwnerDocument.created_at.desc(),
        FranchiseOwnerDocument.id.desc(),
    )
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    offset = (page - 1) * page_size
    rows = db.scalars(stmt.offset(offset).limit(page_size)).all()
    meta = paginated_meta(total, page, page_size)
    return FranchiseOwnerDocumentListResponse(
        items=[_document_to_read(row) for row in rows],
        **meta,
    )


@router.post(
    "/franchise-owner/documents",
    response_model=FranchiseOwnerDocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=255),
    document_type: OwnerDocumentTypeSchema = Form(default=OwnerDocumentTypeSchema.other),
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    relative_path, mime_type, size = save_upload_file(
        file,
        subdir=f"owners/{current_user.user_id}/documents",
        allowed_mime=ALLOWED_DOCUMENT_TYPES,
    )
    doc = FranchiseOwnerDocument(
        franchise_owner_id=current_user.user_id,
        title=title.strip(),
        document_type=OwnerDocumentType(document_type.value),
        file_path=relative_path,
        mime_type=mime_type,
        file_size_bytes=size,
        original_filename=file.filename,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return FranchiseOwnerDocumentUploadResponse(document=_document_to_read(doc))


@router.get(
    "/franchise-owner/territories",
    response_model=BrandTerritoryListResponse,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def list_territories(
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    return list_owner_territories(db, current_user.user_id)


@router.post(
    "/franchise-owner/territories",
    response_model=BrandTerritoryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def create_territory(
    payload: BrandTerritoryCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    return create_owner_territory(db, current_user.user_id, payload)


@router.patch(
    "/franchise-owner/territories/{territory_id}",
    response_model=BrandTerritoryRead,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def update_territory(
    territory_id: int,
    payload: BrandTerritoryUpdate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    return update_owner_territory(db, current_user.user_id, territory_id, payload)


@router.delete(
    "/franchise-owner/territories/{territory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def delete_territory(
    territory_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    delete_owner_territory(db, current_user.user_id, territory_id)


@router.get(
    "/franchise-owner/ecosystem",
    response_model=FranchiseOwnerEcosystemResponse,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def get_ecosystem(
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    return build_franchise_owner_ecosystem(db, current_user.user_id)


@router.get(
    "/franchise-owner/analytics",
    response_model=FranchiseOwnerAnalyticsResponse,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def get_analytics(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    brand = get_owned_brand_optional(db, current_user)
    return build_owner_analytics(
        db,
        franchise_owner_id=current_user.user_id,
        brand_id=brand.id if brand else None,
        days=days,
    )


@router.get(
    "/franchise-owner/analytics/geography",
    response_model=FranchiseOwnerGeographyResponse,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def get_analytics_geography(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    brand = get_owned_brand_optional(db, current_user)
    return build_geography_analytics(
        db,
        franchise_owner_id=current_user.user_id,
        brand_id=brand.id if brand else None,
        days=days,
    )

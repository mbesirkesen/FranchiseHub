from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..agent_service import run_agent_query_only
from ..buyer_service import recommend_brands
from ..database import get_db
from ..dependencies import get_current_principal, require_roles
from ..models import (
    Application,
    ApplicationStatus,
    Brand,
    Buyer,
    BuyerFavorite,
    FranchiseOutlet,
    Inventory,
    SupplyRequest,
    SupplyRequestStatus,
    UserRole,
    OutletStatus,
)
from ..pagination import paginated_meta
from ..product_utils import normalize_product_name
from ..supply_service import validate_buyer_supply_quantity
from ..schemas import (
    AssistantQueryRequest,
    AssistantQueryResponse,
    AuthenticatedPrincipal,
    BuyerApplicationBrandSummary,
    BuyerApplicationDetailResponse,
    BuyerApplicationListItem,
    BuyerApplicationsListResponse,
    BuyerDashboardSummary,
    BuyerFavoritesResponse,
    BuyerQualificationRequest,
    BuyerQualificationResponse,
    BuyerSupplyRequestCreate,
    BrandRead,
    FranchiseOutletRead,
    InventoryRead,
    SupplyRequestRead,
)

router = APIRouter(prefix="/buyer", tags=["buyer"])


def _approved_brand_or_404(db: Session, brand_id: int) -> Brand:
    brand = db.scalar(
        select(Brand).where(Brand.id == brand_id, Brand.is_approved.is_(True))
    )
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found",
        )
    return brand


def _application_for_buyer_or_404(
    db: Session, buyer_id: int, application_id: int
) -> Application:
    app = db.scalar(
        select(Application).where(
            Application.id == application_id,
            Application.buyer_id == buyer_id,
        )
    )
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )
    return app


@router.get(
    "/favorites",
    response_model=BuyerFavoritesResponse,
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def list_favorites(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    base = (
        select(BuyerFavorite.brand_id)
        .where(BuyerFavorite.buyer_id == current_user.user_id)
        .order_by(BuyerFavorite.created_at.desc(), BuyerFavorite.id.desc())
    )
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    offset = (page - 1) * page_size
    brand_ids = list(db.scalars(base.offset(offset).limit(page_size)).all())
    meta = paginated_meta(total, page, page_size)
    return BuyerFavoritesResponse(items=brand_ids, **meta)


@router.post(
    "/favorites/{brand_id}",
    response_model=BuyerFavoritesResponse,
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def add_favorite(
    brand_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    _approved_brand_or_404(db, brand_id)
    existing = db.scalar(
        select(BuyerFavorite).where(
            BuyerFavorite.buyer_id == current_user.user_id,
            BuyerFavorite.brand_id == brand_id,
        )
    )
    if existing is None:
        db.add(BuyerFavorite(buyer_id=current_user.user_id, brand_id=brand_id))
        db.commit()
    rows = db.scalars(
        select(BuyerFavorite.brand_id)
        .where(BuyerFavorite.buyer_id == current_user.user_id)
        .order_by(BuyerFavorite.created_at.desc())
    ).all()
    meta = paginated_meta(len(rows), 1, max(len(rows), 1))
    return BuyerFavoritesResponse(items=list(rows), **meta)


@router.delete(
    "/favorites/{brand_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def remove_favorite(
    brand_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    fav = db.scalar(
        select(BuyerFavorite).where(
            BuyerFavorite.buyer_id == current_user.user_id,
            BuyerFavorite.brand_id == brand_id,
        )
    )
    if not fav:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Favorite not found",
        )
    db.delete(fav)
    db.commit()


@router.get(
    "/applications",
    response_model=BuyerApplicationsListResponse,
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def list_my_applications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    base = (
        select(Application, Brand)
        .join(Brand, Application.brand_id == Brand.id)
        .where(Application.buyer_id == current_user.user_id)
        .order_by(Application.created_at.desc(), Application.id.desc())
    )
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    offset = (page - 1) * page_size
    rows = db.execute(base.offset(offset).limit(page_size)).all()
    items = [
        BuyerApplicationListItem(
            id=app.id,
            brand_id=app.brand_id,
            status=app.status,
            notes=app.notes,
            created_at=app.created_at,
            brand=BuyerApplicationBrandSummary(
                id=brand.id,
                name=brand.name,
                sector=brand.sector,
                location=brand.location,
                initial_cost=brand.initial_cost,
            ),
        )
        for app, brand in rows
    ]
    meta = paginated_meta(total, page, page_size)
    return BuyerApplicationsListResponse(items=items, **meta)


@router.get(
    "/applications/{application_id}",
    response_model=BuyerApplicationDetailResponse,
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def get_my_application(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    app = _application_for_buyer_or_404(db, current_user.user_id, application_id)
    brand = db.get(Brand, app.brand_id)
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found",
        )
    return BuyerApplicationDetailResponse(
        id=app.id,
        buyer_id=app.buyer_id,
        brand_id=app.brand_id,
        status=app.status,
        notes=app.notes,
        created_at=app.created_at,
        brand=BrandRead.model_validate(brand),
    )


@router.get(
    "/dashboard/summary",
    response_model=BuyerDashboardSummary,
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def buyer_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    buyer_id = current_user.user_id
    favorites_count = int(
        db.scalar(
            select(func.count(BuyerFavorite.id)).where(
                BuyerFavorite.buyer_id == buyer_id
            )
        )
        or 0
    )
    pending = int(
        db.scalar(
            select(func.count(Application.id)).where(
                Application.buyer_id == buyer_id,
                Application.status == ApplicationStatus.pending,
            )
        )
        or 0
    )
    approved = int(
        db.scalar(
            select(func.count(Application.id)).where(
                Application.buyer_id == buyer_id,
                Application.status == ApplicationStatus.approved,
            )
        )
        or 0
    )
    rejected = int(
        db.scalar(
            select(func.count(Application.id)).where(
                Application.buyer_id == buyer_id,
                Application.status == ApplicationStatus.rejected,
            )
        )
        or 0
    )
    total = int(
        db.scalar(
            select(func.count(Application.id)).where(Application.buyer_id == buyer_id)
        )
        or 0
    )
    return BuyerDashboardSummary(
        favorites_count=favorites_count,
        applications_pending=pending,
        applications_approved=approved,
        applications_rejected=rejected,
        applications_total=total,
    )


def _assistant_handler(
    payload: AssistantQueryRequest,
    db: Session,
    current_user: AuthenticatedPrincipal,
) -> AssistantQueryResponse:
    buyer = db.get(Buyer, current_user.user_id)
    if not buyer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Buyer not found",
        )
    return run_agent_query_only(db, buyer, payload)


@router.post(
    "/assistant/query",
    response_model=AssistantQueryResponse,
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def buyer_assistant_query(
    payload: AssistantQueryRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    return _assistant_handler(payload, db, current_user)


@router.post(
    "/assistant",
    response_model=AssistantQueryResponse,
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def buyer_assistant(
    payload: AssistantQueryRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    """Frontend alias: POST /buyer/assistant"""
    return _assistant_handler(payload, db, current_user)


@router.post(
    "/qualification",
    response_model=BuyerQualificationResponse,
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def buyer_qualification(
    payload: BuyerQualificationRequest,
    db: Session = Depends(get_db),
):
    items = recommend_brands(
        db,
        investment_budget=payload.investment_budget,
        preferred_sector=payload.preferred_sector,
        experience_years=payload.experience_years,
        city=payload.city,
    )
    return BuyerQualificationResponse(items=items, matching_engine="rules")


def _buyer_supply_to_read(db: Session, row: SupplyRequest) -> SupplyRequestRead:
    outlet_name = None
    if row.outlet_id:
        outlet = db.get(FranchiseOutlet, row.outlet_id)
        outlet_name = outlet.name if outlet else None
    buyer = db.get(Buyer, row.buyer_id) if row.buyer_id else None
    buyer_name = None
    if buyer:
        parts = [buyer.first_name or "", buyer.last_name or ""]
        buyer_name = " ".join(p for p in parts if p).strip() or buyer.email
    return SupplyRequestRead(
        id=row.id,
        franchise_owner_id=row.franchise_owner_id,
        product_name=row.product_name,
        quantity=row.quantity,
        status=row.status,
        outlet_id=row.outlet_id,
        buyer_id=row.buyer_id,
        outlet_name=outlet_name,
        buyer_name=buyer_name,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get(
    "/supply-requests",
    response_model=list[SupplyRequestRead],
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def list_buyer_supply_requests(
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    rows = db.scalars(
        select(SupplyRequest)
        .where(SupplyRequest.buyer_id == current_user.user_id)
        .order_by(SupplyRequest.created_at.desc(), SupplyRequest.id.desc())
    ).all()
    return [_buyer_supply_to_read(db, row) for row in rows]


@router.post(
    "/supply-requests",
    response_model=SupplyRequestRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def create_buyer_supply_request(
    payload: BuyerSupplyRequestCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    approved = db.scalar(
        select(Application).where(
            Application.buyer_id == current_user.user_id,
            Application.brand_id == payload.brand_id,
            Application.status == ApplicationStatus.approved,
        )
    )
    if not approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Supply requests require an approved franchise application",
        )
    brand = db.get(Brand, payload.brand_id)
    if not brand or not brand.franchise_owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found",
        )
    outlet = db.scalar(
        select(FranchiseOutlet).where(
            FranchiseOutlet.id == payload.outlet_id,
            FranchiseOutlet.franchise_owner_id == brand.franchise_owner_id,
        )
    )
    if not outlet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outlet not found for this brand",
        )
    product_name = normalize_product_name(payload.product_name)
    validate_buyer_supply_quantity(
        db,
        franchise_owner_id=brand.franchise_owner_id,
        product_name=product_name,
        quantity=payload.quantity,
    )
    row = SupplyRequest(
        franchise_owner_id=brand.franchise_owner_id,
        buyer_id=current_user.user_id,
        outlet_id=payload.outlet_id,
        product_name=product_name,
        quantity=payload.quantity,
        status=SupplyRequestStatus.pending,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _buyer_supply_to_read(db, row)


@router.get(
    "/brands/{brand_id}/outlets",
    response_model=list[FranchiseOutletRead],
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def list_brand_outlets_for_buyer(
    brand_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    approved = db.scalar(
        select(Application).where(
            Application.buyer_id == current_user.user_id,
            Application.brand_id == brand_id,
            Application.status == ApplicationStatus.approved,
        )
    )
    if not approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Outlet list requires an approved franchise application",
        )
    rows = db.scalars(
        select(FranchiseOutlet).where(
            FranchiseOutlet.brand_id == brand_id,
            FranchiseOutlet.status == OutletStatus.active,
        )
    ).all()
    return list(rows)


@router.get(
    "/brands/{brand_id}/center-inventory",
    response_model=list[InventoryRead],
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def list_brand_center_inventory_for_buyer(
    brand_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    approved = db.scalar(
        select(Application).where(
            Application.buyer_id == current_user.user_id,
            Application.brand_id == brand_id,
            Application.status == ApplicationStatus.approved,
        )
    )
    if not approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Center inventory requires an approved franchise application",
        )
    brand = db.get(Brand, brand_id)
    if not brand or not brand.franchise_owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found",
        )
    rows = db.scalars(
        select(Inventory)
        .where(
            Inventory.franchise_owner_id == brand.franchise_owner_id,
            Inventory.outlet_id.is_(None),
        )
        .order_by(Inventory.item_name.asc(), Inventory.id.asc())
    ).all()
    return list(rows)

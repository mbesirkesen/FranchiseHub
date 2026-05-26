from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_principal, require_roles
from ..models import (
    Application,
    ApplicationStatus,
    Brand,
    Inventory,
    Message,
    SupplyRequest,
    SupplyRequestStatus,
    UserRole,
)
from ..schemas import (
    ApplicationListEnvelope,
    ApplicationRead,
    ApplicationUpdate,
    AuthenticatedPrincipal,
    BrandRead,
    FranchiseOwnerBrandWrite,
    FranchiseOwnerDashboardSummary,
    MessageCreate,
    MessageRead,
)

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
    response_model=BrandRead | None,
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


@router.get(
    "/applications/my-brand",
    response_model=ApplicationListEnvelope,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def list_my_brand_applications(
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    brand = get_owned_brand_optional(db, current_user)
    if brand is None:
        return ApplicationListEnvelope(items=[])
    rows = db.scalars(
        select(Application)
        .where(Application.brand_id == brand.id)
        .order_by(Application.created_at.desc(), Application.id.desc())
    ).all()
    return ApplicationListEnvelope(items=rows)


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


@router.post("/messages", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
def create_message(
    payload: MessageCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    if current_user.role not in {UserRole.franchise_owner, UserRole.buyer}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only buyers and franchise owners can send messages",
        )

    application = db.get(Application, payload.application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )
    if application.status != ApplicationStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Messaging is only available for approved applications",
        )

    if current_user.role == UserRole.buyer and application.buyer_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not part of this application",
        )
    if current_user.role == UserRole.franchise_owner:
        brand = get_owned_brand_or_404(db, current_user)
        if application.brand_id != brand.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not part of this application",
            )

    message = Message(
        application_id=payload.application_id,
        sender_role=current_user.role,
        sender_id=current_user.user_id,
        content=payload.content,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


@router.get("/messages/{application_id}", response_model=list[MessageRead])
def list_messages(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    application = db.get(Application, application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    allowed = False
    if current_user.role == UserRole.buyer and application.buyer_id == current_user.user_id:
        allowed = True
    elif current_user.role == UserRole.franchise_owner:
        brand = db.scalar(
            select(Brand).where(Brand.franchise_owner_id == current_user.user_id)
        )
        if brand and brand.id == application.brand_id:
            allowed = True

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to view these messages",
        )

    return db.scalars(
        select(Message)
        .where(Message.application_id == application_id)
        .order_by(Message.created_at.asc())
    ).all()

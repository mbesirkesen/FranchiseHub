from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..application_access import (
    build_application_detail,
    get_application_or_404,
    require_application_access,
    count_unread_for_user,
)
from ..application_timeline import build_application_timeline
from ..database import get_db
from ..dependencies import get_current_principal, require_roles
from ..models import Application, ApplicationStatus, Brand, UserRole
from ..pagination import paginated_meta
from ..schemas import (
    ApplicationDetailResponse,
    ApplicationMineListItem,
    ApplicationTimelineResponse,
    ApplicationsMineResponse,
    AuthenticatedPrincipal,
    BuyerApplicationBrandSummary,
    BuyerApplicationCreate,
    ApplicationRead,
)

router = APIRouter(tags=["applications"])


@router.post(
    "/applications",
    response_model=ApplicationRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def create_application(
    payload: BuyerApplicationCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    brand = db.get(Brand, payload.brand_id)
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found",
        )
    if not brand.is_approved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Applications are only allowed for approved brands",
        )

    application = Application(
        buyer_id=current_user.user_id,
        brand_id=payload.brand_id,
        status=ApplicationStatus.pending,
        notes=payload.notes,
    )
    db.add(application)
    db.commit()
    db.refresh(application)
    return application


@router.get(
    "/applications/mine",
    response_model=ApplicationsMineResponse,
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
        ApplicationMineListItem(
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
            unread_count=count_unread_for_user(db, app.id, current_user),
        )
        for app, brand in rows
    ]
    meta = paginated_meta(total, page, page_size)
    return ApplicationsMineResponse(items=items, **meta)


@router.get(
    "/applications/{application_id}",
    response_model=ApplicationDetailResponse,
    dependencies=[
        Depends(
            require_roles(UserRole.buyer, UserRole.franchise_owner)
        )
    ],
)
def get_application_detail(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    application = get_application_or_404(db, application_id)
    require_application_access(db, application, current_user)
    return build_application_detail(db, application, current_user)


@router.get(
    "/applications/{application_id}/timeline",
    response_model=ApplicationTimelineResponse,
    dependencies=[
        Depends(require_roles(UserRole.buyer, UserRole.franchise_owner))
    ],
)
def get_application_timeline(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    application = get_application_or_404(db, application_id)
    return build_application_timeline(db, application, current_user)

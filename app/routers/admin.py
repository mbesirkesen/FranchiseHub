from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_roles
from ..models import Admin, Application, Brand, Buyer, FranchiseOwner, UserRole
from ..schemas import (
    ApplicationRead,
    ApplicationUpdate,
    AuthenticatedPrincipal,
    BrandApprovalUpdate,
    BrandRead,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get(
    "/users",
    response_model=list[AuthenticatedPrincipal],
    dependencies=[Depends(require_roles(UserRole.admin))],
)
def list_users(db: Session = Depends(get_db)):
    buyers = db.scalars(select(Buyer)).all()
    owners = db.scalars(select(FranchiseOwner)).all()
    admins = db.scalars(select(Admin)).all()
    return [
        AuthenticatedPrincipal(role=UserRole.buyer, user_id=user.id, email=user.email)
        for user in buyers
    ] + [
        AuthenticatedPrincipal(
            role=UserRole.franchise_owner, user_id=user.id, email=user.email
        )
        for user in owners
    ] + [
        AuthenticatedPrincipal(role=UserRole.admin, user_id=user.id, email=user.email)
        for user in admins
    ]


@router.patch(
    "/brands/{brand_id}/approve",
    response_model=BrandRead,
    dependencies=[Depends(require_roles(UserRole.admin))],
)
def approve_brand(
    brand_id: int,
    payload: BrandApprovalUpdate,
    db: Session = Depends(get_db),
):
    brand = db.get(Brand, brand_id)
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found",
        )

    brand.is_approved = payload.is_approved
    db.commit()
    db.refresh(brand)
    return brand


@router.patch(
    "/applications/{application_id}/override",
    response_model=ApplicationRead,
    dependencies=[Depends(require_roles(UserRole.admin))],
)
def override_application_status(
    application_id: int,
    payload: ApplicationUpdate,
    db: Session = Depends(get_db),
):
    application = db.get(Application, application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    application.status = payload.status
    if payload.notes is not None:
        application.notes = payload.notes

    db.commit()
    db.refresh(application)
    return application

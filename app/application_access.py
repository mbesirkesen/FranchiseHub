from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Application, Brand, Buyer, Message, MessageReadReceipt, UserRole
from .application_status import resolve_extended_status
from .schemas import (
    ApplicationDetailResponse,
    ApplicationParticipantBuyer,
    ApplicationStatus,
    AuthenticatedPrincipal,
    BrandRead,
)


def can_access_application(
    db: Session,
    application: Application,
    principal: AuthenticatedPrincipal,
) -> bool:
    if principal.role == UserRole.buyer:
        return application.buyer_id == principal.user_id
    if principal.role == UserRole.franchise_owner:
        brand = db.scalar(
            select(Brand).where(
                Brand.id == application.brand_id,
                Brand.franchise_owner_id == principal.user_id,
            )
        )
        return brand is not None
    return False


def get_application_or_404(db: Session, application_id: int) -> Application:
    application = db.get(Application, application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )
    return application


def require_application_access(
    db: Session,
    application: Application,
    principal: AuthenticatedPrincipal,
) -> None:
    if not can_access_application(db, application, principal):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to access this application",
        )


def count_messages(db: Session, application_id: int) -> int:
    return int(
        db.scalar(
            select(func.count(Message.id)).where(Message.application_id == application_id)
        )
        or 0
    )


def count_unread_for_user(
    db: Session, application_id: int, principal: AuthenticatedPrincipal
) -> int:
    messages = db.scalars(
        select(Message).where(Message.application_id == application_id)
    ).all()
    if not messages:
        return 0
    read_message_ids = set(
        db.scalars(
            select(MessageReadReceipt.message_id).where(
                MessageReadReceipt.reader_role == principal.role,
                MessageReadReceipt.reader_id == principal.user_id,
            )
        ).all()
    )
    unread = 0
    for msg in messages:
        if msg.sender_role == principal.role and msg.sender_id == principal.user_id:
            continue
        if msg.id not in read_message_ids:
            unread += 1
    return unread


def build_application_detail(
    db: Session,
    application: Application,
    principal: AuthenticatedPrincipal,
) -> ApplicationDetailResponse:
    brand = db.get(Brand, application.brand_id)
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found",
        )
    buyer_payload: Optional[ApplicationParticipantBuyer] = None
    if principal.role == UserRole.franchise_owner:
        buyer = db.get(Buyer, application.buyer_id)
        if buyer:
            buyer_payload = ApplicationParticipantBuyer.model_validate(buyer)

    msg_count = count_messages(db, application.id)
    ext_status, ext_label = resolve_extended_status(application, message_count=msg_count)

    return ApplicationDetailResponse(
        id=application.id,
        buyer_id=application.buyer_id,
        brand_id=application.brand_id,
        status=ApplicationStatus(application.status.value),
        extended_status=ext_status,
        extended_status_label=ext_label,
        notes=application.notes,
        created_at=application.created_at,
        brand=BrandRead.model_validate(brand),
        buyer=buyer_payload,
        message_count=msg_count,
        unread_count=count_unread_for_user(db, application.id, principal),
    )

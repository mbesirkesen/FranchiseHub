from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..application_access import get_application_or_404, require_application_access
from ..database import get_db
from ..dependencies import get_current_principal
from ..messaging_service import (
    list_conversations,
    list_messages_for_user,
    mark_all_messages_read_for_application,
    mark_message_read,
)
from ..models import Application, ApplicationStatus, Brand, Buyer, Message, UserRole
from ..notification_events import notify_new_message
from ..schemas import (
    AuthenticatedPrincipal,
    ConversationsResponse,
    MessageCreate,
    MessageRead,
    MessagesReadAllResponse,
    MessageReadUpdateResponse,
)

router = APIRouter(tags=["messages"])


@router.get("/conversations", response_model=ConversationsResponse)
def get_conversations(
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    return list_conversations(db, current_user)


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

    application = get_application_or_404(db, payload.application_id)
    require_application_access(db, application, current_user)

    if application.status != ApplicationStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Messaging is only available for approved applications",
        )

    message = Message(
        application_id=payload.application_id,
        sender_role=current_user.role,
        sender_id=current_user.user_id,
        content=payload.content,
    )
    db.add(message)
    db.flush()
    brand = db.get(Brand, application.brand_id)
    buyer = db.get(Buyer, application.buyer_id)
    if brand and buyer:
        notify_new_message(
            db,
            message=message,
            application=application,
            brand=brand,
            buyer=buyer,
        )
    db.commit()
    db.refresh(message)
    from ..messaging_service import message_to_read

    return message_to_read(message, principal=current_user, read_at=None)


@router.get("/messages/{application_id}", response_model=list[MessageRead])
def list_messages(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    application = get_application_or_404(db, application_id)
    require_application_access(db, application, current_user)
    return list_messages_for_user(db, application_id, current_user)


@router.post(
    "/messages/{application_id}/read-all",
    response_model=MessagesReadAllResponse,
)
def mark_all_messages_read(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    count = mark_all_messages_read_for_application(db, application_id, current_user)
    return MessagesReadAllResponse(
        application_id=application_id, updated_count=count
    )


@router.patch("/messages/{message_id}/read", response_model=MessageReadUpdateResponse)
def mark_message_as_read(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    if current_user.role not in {UserRole.franchise_owner, UserRole.buyer}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only buyers and franchise owners can mark messages as read",
        )
    _message, read_at = mark_message_read(db, message_id, current_user)
    return MessageReadUpdateResponse(id=message_id, is_read=True, read_at=read_at)

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .application_access import can_access_application, count_unread_for_user
from .models import (
    Application,
    ApplicationStatus,
    Brand,
    Buyer,
    Message,
    MessageReadReceipt,
    UserRole,
)
from .schemas import (
    AuthenticatedPrincipal,
    ConversationItem,
    ConversationLastMessage,
    ConversationsResponse,
    MessageRead,
)


def message_to_read(
    msg: Message,
    *,
    principal: AuthenticatedPrincipal,
    read_at: Optional[datetime] = None,
) -> MessageRead:
    is_own = msg.sender_role == principal.role and msg.sender_id == principal.user_id
    is_read = is_own or read_at is not None
    return MessageRead(
        id=msg.id,
        application_id=msg.application_id,
        sender_role=msg.sender_role,
        sender_id=msg.sender_id,
        content=msg.content,
        created_at=msg.created_at,
        is_read=is_read,
        read_at=read_at,
    )


def get_read_at_for_user(
    db: Session, message_id: int, principal: AuthenticatedPrincipal
) -> Optional[datetime]:
    return db.scalar(
        select(MessageReadReceipt.read_at).where(
            MessageReadReceipt.message_id == message_id,
            MessageReadReceipt.reader_role == principal.role,
            MessageReadReceipt.reader_id == principal.user_id,
        )
    )


def list_messages_for_user(
    db: Session,
    application_id: int,
    principal: AuthenticatedPrincipal,
) -> list[MessageRead]:
    rows = db.scalars(
        select(Message)
        .where(Message.application_id == application_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    ).all()
    result: list[MessageRead] = []
    for msg in rows:
        read_at = get_read_at_for_user(db, msg.id, principal)
        result.append(message_to_read(msg, principal=principal, read_at=read_at))
    return result


def mark_message_read(
    db: Session,
    message_id: int,
    principal: AuthenticatedPrincipal,
) -> tuple[Message, datetime]:
    message = db.get(Message, message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )
    application = db.get(Application, message.application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )
    if not can_access_application(db, application, principal):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to access this message",
        )
    if message.sender_role == principal.role and message.sender_id == principal.user_id:
        return message, message.created_at

    existing = db.scalar(
        select(MessageReadReceipt).where(
            MessageReadReceipt.message_id == message_id,
            MessageReadReceipt.reader_role == principal.role,
            MessageReadReceipt.reader_id == principal.user_id,
        )
    )
    if existing:
        return message, existing.read_at

    receipt = MessageReadReceipt(
        message_id=message_id,
        reader_role=principal.role,
        reader_id=principal.user_id,
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return message, receipt.read_at


def _last_message(db: Session, application_id: int) -> Optional[Message]:
    return db.scalar(
        select(Message)
        .where(Message.application_id == application_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )


def list_conversations(
    db: Session, principal: AuthenticatedPrincipal
) -> ConversationsResponse:
    if principal.role not in {UserRole.buyer, UserRole.franchise_owner}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only buyers and franchise owners have a conversations inbox",
        )

    if principal.role == UserRole.buyer:
        apps = db.scalars(
            select(Application)
            .where(
                Application.buyer_id == principal.user_id,
                Application.status == ApplicationStatus.approved,
            )
            .order_by(Application.created_at.desc(), Application.id.desc())
        ).all()
    else:
        brand_ids = list(
            db.scalars(
                select(Brand.id).where(
                    Brand.franchise_owner_id == principal.user_id
                )
            ).all()
        )
        if not brand_ids:
            return ConversationsResponse(items=[])
        apps = db.scalars(
            select(Application)
            .where(
                Application.brand_id.in_(brand_ids),
                Application.status == ApplicationStatus.approved,
            )
            .order_by(Application.created_at.desc(), Application.id.desc())
        ).all()

    items: list[ConversationItem] = []
    for app in apps:
        brand = db.get(Brand, app.brand_id)
        buyer = db.get(Buyer, app.buyer_id)
        if not brand or not buyer:
            continue
        last = _last_message(db, app.id)
        last_payload = None
        if last:
            last_payload = ConversationLastMessage(
                id=last.id,
                content=last.content[:200],
                sender_role=last.sender_role,
                created_at=last.created_at,
            )
        items.append(
            ConversationItem(
                application_id=app.id,
                application_status=app.status,
                brand_id=brand.id,
                brand_name=brand.name,
                buyer_id=buyer.id,
                buyer_name=f"{buyer.first_name} {buyer.last_name}".strip(),
                unread_count=count_unread_for_user(db, app.id, principal),
                last_message=last_payload,
            )
        )

    def _sort_key(item: ConversationItem) -> tuple:
        last_at = datetime.min
        if item.last_message and item.last_message.created_at:
            last_at = item.last_message.created_at
        return (item.unread_count, last_at)

    items.sort(key=_sort_key, reverse=True)

    return ConversationsResponse(items=items)


def mark_all_messages_read_for_application(
    db: Session,
    application_id: int,
    principal: AuthenticatedPrincipal,
) -> int:
    application = db.get(Application, application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )
    if not can_access_application(db, application, principal):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to access this application",
        )

    messages = db.scalars(
        select(Message).where(Message.application_id == application_id)
    ).all()
    updated = 0
    for msg in messages:
        if msg.sender_role == principal.role and msg.sender_id == principal.user_id:
            continue
        existing = db.scalar(
            select(MessageReadReceipt).where(
                MessageReadReceipt.message_id == msg.id,
                MessageReadReceipt.reader_role == principal.role,
                MessageReadReceipt.reader_id == principal.user_id,
            )
        )
        if existing:
            continue
        db.add(
            MessageReadReceipt(
                message_id=msg.id,
                reader_role=principal.role,
                reader_id=principal.user_id,
            )
        )
        updated += 1
    if updated:
        db.commit()
    return updated

from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .models import DevicePlatform, Notification, PushDevice, UserRole
from .schemas import (
    AuthenticatedPrincipal,
    NotificationListResponse,
    NotificationRead,
)


def _map_notification(row: Notification) -> NotificationRead:
    return NotificationRead(
        id=row.id,
        title=row.title,
        body=row.body,
        notification_type=row.notification_type,
        action_url=row.action_url,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        is_read=row.is_read,
        read_at=row.read_at,
        created_at=row.created_at,
    )


def total_pages(total: int, page_size: int) -> int:
    if total == 0:
        return 0
    return math.ceil(total / page_size)


def list_notifications(
    db: Session,
    principal: AuthenticatedPrincipal,
    *,
    page: int,
    page_size: int,
    unread_only: bool = False,
) -> NotificationListResponse:
    base = select(Notification).where(
        Notification.recipient_role == principal.role,
        Notification.recipient_id == principal.user_id,
    )
    if unread_only:
        base = base.where(Notification.is_read.is_(False))

    count_stmt = select(func.count()).select_from(base.subquery())
    total = int(db.scalar(count_stmt) or 0)

    unread_count = int(
        db.scalar(
            select(func.count(Notification.id)).where(
                Notification.recipient_role == principal.role,
                Notification.recipient_id == principal.user_id,
                Notification.is_read.is_(False),
            )
        )
        or 0
    )

    offset = (page - 1) * page_size
    rows = db.scalars(
        base.order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset(offset)
        .limit(page_size)
    ).all()

    return NotificationListResponse(
        items=[_map_notification(r) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages(total, page_size),
        unread_count=unread_count,
    )


def get_notification_for_user(
    db: Session, principal: AuthenticatedPrincipal, notification_id: int
) -> Notification:
    notification = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_role == principal.role,
            Notification.recipient_id == principal.user_id,
        )
    )
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return notification


def mark_notification_read(
    db: Session, principal: AuthenticatedPrincipal, notification_id: int
) -> tuple[Notification, datetime]:
    notification = get_notification_for_user(db, principal, notification_id)
    now = datetime.utcnow()
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = now
        db.add(notification)
        db.commit()
        db.refresh(notification)
    return notification, notification.read_at or now


def mark_all_notifications_read(
    db: Session, principal: AuthenticatedPrincipal
) -> int:
    now = datetime.utcnow()
    result = db.execute(
        update(Notification)
        .where(
            Notification.recipient_role == principal.role,
            Notification.recipient_id == principal.user_id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True, read_at=now)
    )
    db.commit()
    return int(result.rowcount or 0)


def register_push_device(
    db: Session,
    principal: AuthenticatedPrincipal,
    *,
    token: str,
    platform: DevicePlatform,
) -> PushDevice:
    existing = db.scalar(
        select(PushDevice).where(
            PushDevice.recipient_role == principal.role,
            PushDevice.recipient_id == principal.user_id,
            PushDevice.token == token,
        )
    )
    now = datetime.utcnow()
    if existing:
        existing.platform = platform
        existing.updated_at = now
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    device = PushDevice(
        recipient_role=principal.role,
        recipient_id=principal.user_id,
        token=token,
        platform=platform,
        updated_at=now,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def delete_push_device(
    db: Session, principal: AuthenticatedPrincipal, token: str
) -> None:
    device = db.scalar(
        select(PushDevice).where(
            PushDevice.token == token,
            PushDevice.recipient_role == principal.role,
            PushDevice.recipient_id == principal.user_id,
        )
    )
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device token not found",
        )
    db.delete(device)
    db.commit()


def create_notification(
    db: Session,
    *,
    recipient_role: UserRole,
    recipient_id: int,
    title: str,
    body: str,
    notification_type: str = "general",
    action_url: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
) -> Notification:
    notification = Notification(
        recipient_role=recipient_role,
        recipient_id=recipient_id,
        title=title,
        body=body,
        notification_type=notification_type,
        action_url=action_url,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    db.add(notification)
    db.flush()
    return notification

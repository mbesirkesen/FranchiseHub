from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_principal
from ..models import DevicePlatform
from ..notification_service import (
    delete_push_device,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    register_push_device,
)
from ..schemas import (
    AuthenticatedPrincipal,
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    NotificationListResponse,
    NotificationReadAllResponse,
    NotificationReadResponse,
    PushDeviceRead,
)

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=NotificationListResponse)
def get_notifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    unread_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    return list_notifications(
        db,
        current_user,
        page=page,
        page_size=page_size,
        unread_only=unread_only,
    )


@router.patch("/notifications/{notification_id}/read", response_model=NotificationReadResponse)
def mark_notification_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    notification, read_at = mark_notification_read(db, current_user, notification_id)
    return NotificationReadResponse(
        id=notification.id,
        is_read=notification.is_read,
        read_at=read_at,
    )


@router.post("/notifications/read-all", response_model=NotificationReadAllResponse)
def mark_all_as_read(
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    count = mark_all_notifications_read(db, current_user)
    return NotificationReadAllResponse(updated_count=count)


@router.post("/devices", response_model=DeviceRegisterResponse, status_code=status.HTTP_201_CREATED)
def register_device(
    payload: DeviceRegisterRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    device = register_push_device(
        db,
        current_user,
        token=payload.token.strip(),
        platform=DevicePlatform(payload.platform.value),
    )
    return DeviceRegisterResponse(
        device=PushDeviceRead.model_validate(device),
        message="Device registered",
    )


@router.delete("/devices/{token:path}", status_code=status.HTTP_204_NO_CONTENT)
def unregister_device(
    token: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    delete_push_device(db, current_user, token.strip())

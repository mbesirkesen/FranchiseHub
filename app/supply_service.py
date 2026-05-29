from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .models import SupplyRequest, SupplyRequestStatus
from .schemas import SupplyRequestStatus as SupplyRequestStatusSchema


_ALLOWED_PATCH_STATUSES = {
    SupplyRequestStatus.approved,
    SupplyRequestStatus.rejected,
    SupplyRequestStatus.shipped,
}

_TRANSITIONS: dict[SupplyRequestStatus, set[SupplyRequestStatus]] = {
    SupplyRequestStatus.pending: {
        SupplyRequestStatus.approved,
        SupplyRequestStatus.rejected,
    },
    SupplyRequestStatus.approved: {
        SupplyRequestStatus.shipped,
        SupplyRequestStatus.rejected,
    },
    SupplyRequestStatus.shipped: set(),
    SupplyRequestStatus.rejected: set(),
}


def get_supply_request_for_owner(
    db: Session, request_id: int, owner_id: int
) -> SupplyRequest:
    item = db.get(SupplyRequest, request_id)
    if not item or item.franchise_owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supply request not found",
        )
    return item


def update_supply_request_status(
    db: Session,
    request: SupplyRequest,
    *,
    new_status: SupplyRequestStatusSchema,
    notes: Optional[str],
) -> SupplyRequest:
    target = SupplyRequestStatus(new_status.value)
    if target not in _ALLOWED_PATCH_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status must be approved, rejected, or shipped",
        )
    allowed = _TRANSITIONS.get(request.status, set())
    if request.status != target and target not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition from {request.status.value} to {target.value}",
        )
    request.status = target
    if notes is not None:
        request.notes = notes
    request.updated_at = datetime.utcnow()
    db.add(request)
    db.commit()
    db.refresh(request)
    return request

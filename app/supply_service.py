from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Inventory, SupplyRequest, SupplyRequestStatus
from .product_utils import normalize_product_name, product_names_match
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


def find_inventory_by_product(
    db: Session,
    owner_id: int,
    product_name: str,
    *,
    outlet_id: Optional[int],
) -> Inventory | None:
    stmt = select(Inventory).where(Inventory.franchise_owner_id == owner_id)
    if outlet_id is None:
        stmt = stmt.where(Inventory.outlet_id.is_(None))
    else:
        stmt = stmt.where(Inventory.outlet_id == outlet_id)
    for row in db.scalars(stmt).all():
        if product_names_match(row.item_name, product_name):
            return row
    return None


def validate_buyer_supply_quantity(
    db: Session,
    *,
    franchise_owner_id: int,
    product_name: str,
    quantity: int,
) -> None:
    """Talep adedi merkez deposundaki stoktan fazla olamaz."""
    normalized = normalize_product_name(product_name)
    center = find_inventory_by_product(
        db, franchise_owner_id, normalized, outlet_id=None
    )
    if center is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Merkez deposunda “{normalized}” bulunamadı. Listeden ürün seçin.",
        )
    available = int(center.stock_level or 0)
    if quantity > available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Merkezde en fazla {available} adet talep edilebilir.",
        )


def apply_supply_to_inventory(db: Session, request: SupplyRequest) -> None:
    """Sevkiyat: merkez deposundan düş, ilgili şube stoğuna ekle."""
    outlet_id = request.outlet_id
    if outlet_id is None:
        return

    product_name = normalize_product_name(request.product_name)
    request.product_name = product_name

    center = find_inventory_by_product(
        db, request.franchise_owner_id, product_name, outlet_id=None
    )
    if center is None or center.stock_level < request.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Merkez deposunda “{product_name}” için yeterli stok yok. "
                "Merkez deposu sekmesinden aynı ürün adıyla stok ekleyin."
            ),
        )

    center.stock_level -= request.quantity
    db.add(center)

    threshold = center.low_stock_threshold
    outlet_row = find_inventory_by_product(
        db, request.franchise_owner_id, product_name, outlet_id=outlet_id
    )
    if outlet_row:
        outlet_row.stock_level += request.quantity
        db.add(outlet_row)
        return

    db.add(
        Inventory(
            franchise_owner_id=request.franchise_owner_id,
            outlet_id=outlet_id,
            item_name=product_name,
            stock_level=request.quantity,
            low_stock_threshold=threshold,
        )
    )


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
    previous_status = request.status
    request.status = target
    if notes is not None:
        request.notes = notes
    request.updated_at = datetime.utcnow()
    db.add(request)

    if (
        previous_status != SupplyRequestStatus.shipped
        and target == SupplyRequestStatus.shipped
    ):
        apply_supply_to_inventory(db, request)

    db.commit()
    db.refresh(request)
    return request

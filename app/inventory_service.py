from __future__ import annotations

from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import FranchiseOutlet, Inventory, InventoryTransfer
from .schemas import AuthenticatedPrincipal, LowStockInventoryItem


def get_inventory_for_owner(
    db: Session, inventory_id: int, owner_id: int
) -> Inventory:
    item = db.get(Inventory, inventory_id)
    if not item or item.franchise_owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )
    return item


def _outlet_belongs_to_owner(
    db: Session, owner_id: int, outlet_id: Optional[int]
) -> bool:
    if outlet_id is None:
        return True
    found = db.scalar(
        select(FranchiseOutlet.id).where(
            FranchiseOutlet.id == outlet_id,
            FranchiseOutlet.franchise_owner_id == owner_id,
        )
    )
    return found is not None


def transfer_between_outlets(
    db: Session,
    current_user: AuthenticatedPrincipal,
    *,
    inventory_id: int,
    from_outlet_id: Optional[int],
    to_outlet_id: Optional[int],
    quantity: int,
) -> Tuple[InventoryTransfer, Inventory, Inventory]:
    if from_outlet_id == to_outlet_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source and destination outlets must differ",
        )
    if not _outlet_belongs_to_owner(db, current_user.user_id, from_outlet_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source outlet not found",
        )
    if not _outlet_belongs_to_owner(db, current_user.user_id, to_outlet_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Destination outlet not found",
        )

    source = get_inventory_for_owner(db, inventory_id, current_user.user_id)
    if source.outlet_id != from_outlet_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inventory item is not at the specified source outlet",
        )
    if source.stock_level < quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient stock for transfer",
        )

    dest = db.scalar(
        select(Inventory).where(
            Inventory.franchise_owner_id == current_user.user_id,
            Inventory.outlet_id == to_outlet_id,
            Inventory.item_name == source.item_name,
        )
    )
    if dest is None:
        dest = Inventory(
            franchise_owner_id=current_user.user_id,
            outlet_id=to_outlet_id,
            item_name=source.item_name,
            stock_level=0,
            low_stock_threshold=source.low_stock_threshold,
        )
        db.add(dest)
        db.flush()

    source.stock_level -= quantity
    dest.stock_level += quantity

    transfer = InventoryTransfer(
        franchise_owner_id=current_user.user_id,
        from_outlet_id=from_outlet_id,
        to_outlet_id=to_outlet_id,
        inventory_id=source.id,
        item_name=source.item_name,
        quantity=quantity,
    )
    db.add(transfer)
    db.commit()
    db.refresh(transfer)
    db.refresh(source)
    db.refresh(dest)
    return transfer, source, dest


def list_low_stock_items(
    db: Session, owner_id: int, *, scope: Optional[str] = None
) -> list[LowStockInventoryItem]:
    stmt = select(Inventory).where(Inventory.franchise_owner_id == owner_id)
    if scope == "center":
        stmt = stmt.where(Inventory.outlet_id.is_(None))
    elif scope == "outlet":
        stmt = stmt.where(Inventory.outlet_id.isnot(None))
    rows = db.scalars(stmt).all()
    items: list[LowStockInventoryItem] = []
    for row in rows:
        if row.stock_level < row.low_stock_threshold:
            base = LowStockInventoryItem.model_validate(row)
            items.append(
                base.model_copy(
                    update={"deficit": row.low_stock_threshold - row.stock_level}
                )
            )
    items.sort(key=lambda x: x.deficit, reverse=True)
    return items

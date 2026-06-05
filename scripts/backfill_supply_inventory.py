"""Daha önce shipped olup depoya yansımamış siparişleri envantere işler."""

from __future__ import annotations

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Inventory, SupplyRequest, SupplyRequestStatus
from app.supply_service import apply_supply_to_inventory


def main() -> None:
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(SupplyRequest).where(SupplyRequest.status == SupplyRequestStatus.shipped)
        ).all()
        updated = 0
        for request in rows:
            exists = db.scalar(
                select(Inventory.id).where(
                    Inventory.franchise_owner_id == request.franchise_owner_id,
                    Inventory.item_name == request.product_name,
                )
            )
            if exists:
                continue
            apply_supply_to_inventory(db, request)
            updated += 1
        db.commit()
        print(f"Backfill tamam: {updated} sipariş depoya işlendi.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

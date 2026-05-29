from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .brand_service import build_territory_list
from .models import Brand, BrandTerritory, TerritoryStatus
from .schemas import BrandTerritoryCreate, BrandTerritoryRead, BrandTerritoryUpdate


def _brand_for_owner(db: Session, franchise_owner_id: int) -> Brand:
    brand = db.scalar(
        select(Brand).where(Brand.franchise_owner_id == franchise_owner_id)
    )
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found for this franchise owner",
        )
    return brand


def list_owner_territories(db: Session, franchise_owner_id: int):
    brand = _brand_for_owner(db, franchise_owner_id)
    return build_territory_list(db, brand.id)


def create_owner_territory(
    db: Session, franchise_owner_id: int, payload: BrandTerritoryCreate
) -> BrandTerritoryRead:
    brand = _brand_for_owner(db, franchise_owner_id)
    row = BrandTerritory(
        brand_id=brand.id,
        name=payload.name.strip(),
        region_code=payload.region_code,
        status=TerritoryStatus(payload.status.value),
        notes=payload.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return BrandTerritoryRead.model_validate(row)


def update_owner_territory(
    db: Session,
    franchise_owner_id: int,
    territory_id: int,
    payload: BrandTerritoryUpdate,
) -> BrandTerritoryRead:
    brand = _brand_for_owner(db, franchise_owner_id)
    row = db.scalar(
        select(BrandTerritory).where(
            BrandTerritory.id == territory_id,
            BrandTerritory.brand_id == brand.id,
        )
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Territory not found",
        )
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key == "name" and value is not None:
            value = str(value).strip()
        elif key == "status" and value is not None:
            value = TerritoryStatus(value.value)
        setattr(row, key, value)
    db.add(row)
    db.commit()
    db.refresh(row)
    return BrandTerritoryRead.model_validate(row)


def delete_owner_territory(
    db: Session, franchise_owner_id: int, territory_id: int
) -> None:
    brand = _brand_for_owner(db, franchise_owner_id)
    row = db.scalar(
        select(BrandTerritory).where(
            BrandTerritory.id == territory_id,
            BrandTerritory.brand_id == brand.id,
        )
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Territory not found",
        )
    db.delete(row)
    db.commit()

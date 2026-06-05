from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Application, Brand, Buyer, BuyerFavorite


@dataclass
class AgentBuyerContext:
    exclude_brand_ids: set[int] = field(default_factory=set)
    favorite_brand_ids: list[int] = field(default_factory=list)
    applied_brand_ids: list[int] = field(default_factory=list)
    recent_turns: list[tuple[str, str]] = field(default_factory=list)  # (role, content)
    last_search_state: Optional[dict] = None  # {filters_applied, related_brand_ids}


def load_buyer_context(db: Session, buyer: Buyer) -> AgentBuyerContext:
    favorite_ids = [
        int(x)
        for x in db.scalars(
            select(BuyerFavorite.brand_id).where(BuyerFavorite.buyer_id == buyer.id)
        ).all()
    ]
    applied_ids = [
        int(x)
        for x in db.scalars(
            select(Application.brand_id).where(Application.buyer_id == buyer.id)
        ).all()
    ]
    return AgentBuyerContext(
        favorite_brand_ids=favorite_ids,
        applied_brand_ids=applied_ids,
    )


def favorite_brands(db: Session, buyer_id: int) -> list[Brand]:
    ids = [
        int(x)
        for x in db.scalars(
            select(BuyerFavorite.brand_id).where(BuyerFavorite.buyer_id == buyer_id)
        ).all()
    ]
    if not ids:
        return []
    return list(
        db.scalars(
            select(Brand).where(Brand.id.in_(ids), Brand.is_approved.is_(True))
        ).all()
    )

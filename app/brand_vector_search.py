from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .agent_config import AGENT_SEMANTIC_MAX_DISTANCE
from .agent_embeddings import (
    brand_content,
    content_hash,
    embed_text,
    embeddings_available,
)
from .models import Brand, BrandEmbedding

_log = logging.getLogger("franchisehub.agent.vector")


def ensure_brand_indexed(db: Session, brand: Brand, *, commit: bool = True) -> bool:
    """Markanın embedding'i yoksa veya içeriği değiştiyse (yeniden) üret.
    Döner: indexlendi mi (True) / atlandı mı (False)."""
    if not embeddings_available():
        return False
    text = brand_content(brand)
    if not text:
        return False
    digest = content_hash(text)
    row = db.get(BrandEmbedding, brand.id)
    if row is not None and row.content_hash == digest:
        return False
    vec = embed_text(text)
    if vec is None:
        return False
    if row is None:
        row = BrandEmbedding(
            brand_id=brand.id,
            embedding=vec,
            content_hash=digest,
            updated_at=datetime.utcnow(),
        )
        db.add(row)
    else:
        row.embedding = vec
        row.content_hash = digest
        row.updated_at = datetime.utcnow()
    if commit:
        db.commit()
    else:
        db.flush()
    return True


def reindex_all(db: Session, *, only_approved: bool = True) -> int:
    """Tüm (onaylı) markaları indexler. İndexlenen/güncellenen sayısını döner."""
    if not embeddings_available():
        _log.warning("embeddings unavailable, reindex skipped")
        return 0
    stmt = select(Brand)
    if only_approved:
        stmt = stmt.where(Brand.is_approved.is_(True))
    brands = db.scalars(stmt).all()
    count = 0
    for brand in brands:
        if ensure_brand_indexed(db, brand, commit=False):
            count += 1
    db.commit()
    _log.info("reindexed %s/%s brands", count, len(brands))
    return count


def _ensure_all_indexed(db: Session) -> None:
    """Arama öncesi: embedding'i eksik onaylı markaları lazy indexle."""
    indexed_ids = set(db.scalars(select(BrandEmbedding.brand_id)).all())
    stmt = select(Brand).where(Brand.is_approved.is_(True))
    if indexed_ids:
        stmt = stmt.where(Brand.id.notin_(indexed_ids))
    missing = db.scalars(stmt).all()
    if not missing:
        return
    changed = False
    for brand in missing:
        if ensure_brand_indexed(db, brand, commit=False):
            changed = True
    if changed:
        db.commit()


def semantic_brand_search(
    db: Session,
    query: str,
    *,
    sector: Optional[str] = None,
    location: Optional[str] = None,
    min_cost: Optional[float] = None,
    max_cost: Optional[float] = None,
    limit: int = 8,
    max_distance: Optional[float] = None,
) -> list[int]:
    """Sorguya anlamca en yakın onaylı marka id'leri (cosine mesafesine göre sıralı).
    Bütçe/şehir/sektör kesin filtreleri SQL'de uygulanır. Embedding yoksa boş döner."""
    if not embeddings_available() or not query or not query.strip():
        return []
    _ensure_all_indexed(db)
    qvec = embed_text(query)
    if qvec is None:
        return []

    threshold = max_distance if max_distance is not None else AGENT_SEMANTIC_MAX_DISTANCE
    distance = BrandEmbedding.embedding.cosine_distance(qvec)
    stmt = (
        select(Brand.id, distance.label("dist"))
        .join(BrandEmbedding, BrandEmbedding.brand_id == Brand.id)
        .where(Brand.is_approved.is_(True))
    )
    if sector:
        stmt = stmt.where(Brand.sector.ilike(f"%{sector}%"))
    if location:
        stmt = stmt.where(Brand.location.ilike(f"%{location}%"))
    if min_cost is not None:
        stmt = stmt.where(Brand.initial_cost >= min_cost)
    if max_cost is not None:
        stmt = stmt.where(Brand.initial_cost <= max_cost)
    stmt = stmt.order_by(distance.asc()).limit(limit * 2)

    rows = db.execute(stmt).all()
    ids: list[int] = []
    for brand_id, dist in rows:
        if dist is not None and float(dist) <= threshold:
            ids.append(int(brand_id))
        if len(ids) >= limit:
            break
    return ids

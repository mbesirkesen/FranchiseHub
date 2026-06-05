from __future__ import annotations

import time
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .agent_nlu_helpers import normalize_agent_text as _normalize
from .models import Brand

_CACHE_TTL_SECONDS = 90
_cached_vocab: tuple[float, AgentVocabulary] | None = None


@dataclass
class AgentVocabulary:
    """Onaylı markalardan türetilen canlı sözlük — yeni marka eklenince otomatik güncellenir."""

    sectors: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    brand_entries: list[tuple[int, str]] = field(default_factory=list)  # (id, name)
    name_tokens: set[str] = field(default_factory=set)

    def match_sector(self, norm: str) -> str | None:
        best: tuple[int, str] | None = None
        for sector in self.sectors:
            s_norm = _normalize(sector)
            if not s_norm or len(s_norm) < 2:
                continue
            if s_norm in norm:
                score = len(s_norm)
                if best is None or score > best[0]:
                    best = (score, sector)
            for token in s_norm.split():
                if len(token) >= 3 and token in norm:
                    score = len(token)
                    if best is None or score > best[0]:
                        best = (score, sector)
        return best[1] if best else None

    def match_location(self, norm: str) -> str | None:
        best: tuple[int, str] | None = None
        for location in self.locations:
            loc_norm = _normalize(location)
            if not loc_norm:
                continue
            city_key = loc_norm.split()[0] if loc_norm else loc_norm
            if len(city_key) >= 3 and city_key in norm:
                score = len(city_key)
                if best is None or score > best[0]:
                    best = (score, location)
            if loc_norm in norm:
                score = len(loc_norm)
                if best is None or score > best[0]:
                    best = (score, location)
        return best[1] if best else None

    def match_brand_ids(self, norm: str, *, limit: int = 4) -> list[int]:
        found: list[tuple[int, int, str]] = []
        for brand_id, name in self.brand_entries:
            name_norm = _normalize(name)
            if not name_norm:
                continue
            score = 0
            if name_norm in norm:
                score = len(name_norm) + 10
            else:
                for token in name_norm.split():
                    if len(token) >= 3 and token in norm:
                        score = max(score, len(token))
                first = name_norm.split()[0]
                if len(first) >= 4 and first in norm:
                    score = max(score, len(first))
            if score > 0:
                found.append((score, brand_id, name))
        found.sort(key=lambda x: (-x[0], x[2]))
        ids: list[int] = []
        seen: set[int] = set()
        for _, bid, _ in found:
            if bid not in seen:
                seen.add(bid)
                ids.append(bid)
            if len(ids) >= limit:
                break
        return ids

    def extract_search_tokens(self, norm: str) -> list[str]:
        tokens = [t for t in norm.split() if len(t) >= 3 and t in self.name_tokens]
        return tokens[:3]


def load_agent_vocabulary(db: Session, *, force_refresh: bool = False) -> AgentVocabulary:
    global _cached_vocab
    now = time.time()
    if not force_refresh and _cached_vocab and (now - _cached_vocab[0]) < _CACHE_TTL_SECONDS:
        return _cached_vocab[1]

    brands = db.scalars(select(Brand).where(Brand.is_approved.is_(True))).all()
    sectors = sorted({b.sector.strip() for b in brands if b.sector and b.sector.strip()})
    locations = sorted({b.location.strip() for b in brands if b.location and b.location.strip()})
    brand_entries = [(int(b.id), b.name.strip()) for b in brands if b.name and b.name.strip()]

    tokens: set[str] = set()
    for _, name in brand_entries:
        for part in _normalize(name).split():
            if len(part) >= 3:
                tokens.add(part)
    for sector in sectors:
        for part in _normalize(sector).split():
            if len(part) >= 3:
                tokens.add(part)

    vocab = AgentVocabulary(
        sectors=sectors,
        locations=locations,
        brand_entries=brand_entries,
        name_tokens=tokens,
    )
    _cached_vocab = (now, vocab)
    return vocab


def invalidate_agent_vocabulary_cache() -> None:
    global _cached_vocab
    _cached_vocab = None

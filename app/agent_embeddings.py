from __future__ import annotations

import hashlib
import logging
import threading
from typing import Optional

from .agent_config import AGENT_EMBEDDING_ENABLED, AGENT_EMBEDDING_MODEL
from .models import Brand

_log = logging.getLogger("franchisehub.agent.embeddings")

_model = None
_model_lock = threading.Lock()
_load_failed = False


def _get_model():
    """fastembed modelini lazy yükle. Yüklenemezse None döner (semantik arama
    sessizce devre dışı kalır)."""
    global _model, _load_failed
    if _model is not None:
        return _model
    if _load_failed or not AGENT_EMBEDDING_ENABLED:
        return None
    with _model_lock:
        if _model is not None:
            return _model
        if _load_failed:
            return None
        try:
            from fastembed import TextEmbedding

            _model = TextEmbedding(model_name=AGENT_EMBEDDING_MODEL)
            _log.info("embedding model loaded: %s", AGENT_EMBEDDING_MODEL)
        except Exception as exc:  # pragma: no cover - ortam bağımlı
            _load_failed = True
            _log.warning("embedding model load failed, semantic search disabled: %s", exc)
            return None
    return _model


def embeddings_available() -> bool:
    return _get_model() is not None


def embed_text(text: str) -> Optional[list[float]]:
    model = _get_model()
    if model is None or not text or not text.strip():
        return None
    try:
        vec = next(iter(model.embed([text])))
        return [float(x) for x in vec]
    except Exception as exc:  # pragma: no cover
        _log.warning("embed_text failed: %s", exc)
        return None


def embed_texts(texts: list[str]) -> Optional[list[list[float]]]:
    model = _get_model()
    if model is None or not texts:
        return None
    try:
        return [[float(x) for x in v] for v in model.embed(texts)]
    except Exception as exc:  # pragma: no cover
        _log.warning("embed_texts failed: %s", exc)
        return None


# Sektör adı tek başına zayıf semantik sinyal verdiği için eş anlamlı/ilişkili
# kavramlarla zenginleştiriyoruz. Bu, "spor salonu", "araba tamiri", "kuyumcu"
# gibi sorguların doğru sektöre yaklaşmasını sağlar.
_SECTOR_SYNONYMS: dict[str, str] = {
    "gıda": "restoran yemek fast food lokanta burger döner pizza kebap",
    "gida": "restoran yemek fast food lokanta burger döner pizza kebap",
    "kahve": "kafe coffee kahve dükkanı kahvaltı pasta tatlı",
    "kafe": "kafe coffee kahve dükkanı kahvaltı pasta tatlı",
    "sağlık": "fitness spor salonu gym sağlık klinik diyet wellness",
    "saglik": "fitness spor salonu gym sağlık klinik diyet wellness",
    "spor": "fitness spor salonu gym antrenman",
    "otomotiv": "araba oto araç lastik servis tamir yedek parça yıkama",
    "güzellik": "kuaför berber güzellik salonu bakım cilt saç tırnak makyaj spa",
    "guzellik": "kuaför berber güzellik salonu bakım cilt saç tırnak makyaj spa",
    "eğitim": "kurs okul eğitim çocuk anaokulu etüt dershane stem",
    "egitim": "kurs okul eğitim çocuk anaokulu etüt dershane stem",
    "perakende": "mağaza market alışveriş satış dükkan ürün",
    "hizmet": "temizlik hizmet servis kuru temizleme bakım danışmanlık",
}


def brand_content(brand: Brand) -> str:
    """Markanın semantik içeriği: ad + sektör (+ eş anlamlılar) + konum + açıklama."""
    parts = [brand.name or ""]
    if brand.sector:
        parts.append(brand.sector)
        syn = _SECTOR_SYNONYMS.get(brand.sector.strip().lower())
        if syn:
            parts.append(syn)
    if brand.location:
        parts.append(brand.location)
    if brand.description:
        parts.append(brand.description)
    return " — ".join(p.strip() for p in parts if p and p.strip())


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:64]

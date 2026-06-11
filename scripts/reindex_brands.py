"""
Onaylı markaların semantik arama embedding'lerini (pgvector) yeniden üretir.

  python scripts/reindex_brands.py

İçeriği değişmemiş markalar atlanır (content_hash). Yeni/güncellenen markalar
zaten ilk aramada lazy indexlenir; bu script toplu/önden indexleme içindir.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agent_embeddings import embeddings_available
from app.brand_vector_search import reindex_all
from app.database import SessionLocal


def main() -> int:
    if not embeddings_available():
        print("Embedding modeli yüklenemedi; semantik arama devre dışı.")
        return 1
    with SessionLocal() as db:
        count = reindex_all(db)
    print(f"Tamamlandı: {count} marka indexlendi/güncellendi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

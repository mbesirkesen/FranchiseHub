#!/usr/bin/env python3
"""Mevcut DB kayitlarindan [DEMO] isaretlerini temizler."""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import engine  # noqa: E402

_UPDATES: list[tuple[str, str, str]] = [
    ("brands", "support_details", "support_details LIKE '%[DEMO]%'"),
    ("brands", "description", "description LIKE '%[DEMO]%'"),
    (
        "franchise_owners",
        "company_address",
        "company_address LIKE '%[DEMO]%'",
    ),
    ("brand_territories", "name", "name LIKE '%[DEMO]%'"),
    ("franchise_outlets", "name", "name LIKE '%[DEMO]%'"),
    ("brand_fdd_documents", "title", "title LIKE '%[DEMO]%'"),
    ("inventories", "item_name", "item_name LIKE '%[DEMO]%'"),
    ("supply_requests", "product_name", "product_name LIKE '%[DEMO]%'"),
    (
        "franchise_owner_documents",
        "title",
        "title LIKE '%[DEMO]%'",
    ),
    ("applications", "notes", "notes LIKE '%[DEMO]%'"),
]


def strip_demo_markers() -> None:
    for table, column, where in _UPDATES:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    f"""
                    UPDATE {table}
                    SET {column} = TRIM(BOTH FROM REPLACE(
                        REPLACE({column}, '[DEMO] ', ''),
                        ' — [DEMO]', ''
                    ))
                    WHERE {where}
                    """
                )
            )
            print(f"{table}.{column}: {result.rowcount} satir guncellendi")


if __name__ == "__main__":
    strip_demo_markers()
    print("Tamamlandi.")

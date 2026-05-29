"""
Tum uygulama verisini siler (sema / migration'lara dokunmaz).

  python scripts/reset_database.py
  python scripts/reset_database.py --yes   # onay sormadan
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import engine

# FK sirasi — CASCADE ile tek komutta da olur
TRUNCATE_TABLES = [
    "agent_messages",
    "agent_sessions",
    "message_read_receipts",
    "messages",
    "applications",
    "buyer_favorites",
    "brand_fdd_documents",
    "brand_media",
    "brand_territories",
    "inventory_transfers",
    "inventories",
    "franchise_owner_documents",
    "franchise_outlets",
    "supply_requests",
    "brands",
    "push_devices",
    "notifications",
    "uploaded_files",
    "auth_tokens",
    "buyers",
    "franchise_owners",
]


def reset(*, skip_confirm: bool = False) -> None:
    if not skip_confirm:
        print("UYARI: Tum kullanici, marka, basvuru ve mesaj verisi silinecek.")
        if input("Devam? [y/N] ").strip().lower() != "y":
            print("Iptal.")
            return

    tables_sql = ", ".join(TRUNCATE_TABLES)
    with engine.begin() as conn:
        conn.execute(
            text(f"TRUNCATE TABLE {tables_sql} RESTART IDENTITY CASCADE")
        )

    print(f"Temizlendi: {len(TRUNCATE_TABLES)} tablo (ID sayaclari sifirlandi).")
    print("Sonraki adim: python scripts/seed_test_users.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", "-y", action="store_true", help="Onay sorma")
    args = parser.parse_args()
    reset(skip_confirm=args.yes)

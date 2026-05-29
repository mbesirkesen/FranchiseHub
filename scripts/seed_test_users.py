"""
Buyuk demo veri seti — agent / discover / mesajlasma testleri.

  python scripts/seed_test_users.py --reset
  python scripts/seed_test_users.py --reset --buyers 30 --owners 30

Varsayilan: 30 alici + 30 franchise sahibi (60 kullanici, 30 marka).
"""
from __future__ import annotations

import argparse
import importlib.util
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import SessionLocal
from app.models import (
    Application,
    ApplicationStatus,
    Brand,
    BrandFDDDocument,
    BrandMedia,
    BrandMediaType,
    BrandTerritory,
    Buyer,
    BuyerFavorite,
    DevicePlatform,
    FranchiseOutlet,
    FranchiseOwner,
    FranchiseOwnerDocument,
    Inventory,
    Message,
    MessageReadReceipt,
    Notification,
    OutletStatus,
    OwnerDocumentType,
    PushDevice,
    SupplyRequest,
    SupplyRequestStatus,
    TerritoryStatus,
    UserRole,
)
from app.security import hash_password
from app.storage import ensure_upload_root

sys.path.insert(0, str(ROOT_DIR / "scripts"))
from seed_data_generators import (  # noqa: E402
    generate_applications_and_chats,
    generate_buyers,
    generate_owners,
)

random.seed(42)

DEMO = "[DEMO]"
PASSWORD_BUYER = "Buyer12345!"
PASSWORD_OWNER = "Owner12345!"

_MINI_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
)

_STATUS_MAP = {
    "approved": ApplicationStatus.approved,
    "pending": ApplicationStatus.pending,
    "rejected": ApplicationStatus.rejected,
}


def _write_placeholder(relative: str) -> str:
    root = ensure_upload_root()
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(_MINI_PNG)
    return relative


def _get_or_create_owner(db, spec: dict) -> tuple[FranchiseOwner, Brand]:
    owner = db.scalar(select(FranchiseOwner).where(FranchiseOwner.email == spec["email"]))
    if owner is None:
        owner = FranchiseOwner(
            email=spec["email"],
            hashed_password=hash_password(PASSWORD_OWNER),
            company_name=spec["company"],
            tax_number=spec["tax"],
            phone="+9055500" + str(abs(hash(spec["email"])) % 100000).zfill(5),
            authorized_person_name=spec["person"],
            country="Türkiye",
            city=spec["city"],
            company_address=f"{spec['city']} merkez ofis — {DEMO}",
            website=f"https://demo-{abs(hash(spec['email'])) % 99999}.local",
            verification_status=True,
            email_verified=True,
        )
        db.add(owner)
        db.flush()

    bspec = spec["brand"]
    brand = db.scalar(
        select(Brand).where(
            Brand.franchise_owner_id == owner.id,
            Brand.name == bspec["name"],
        )
    )
    if brand is None:
        brand = Brand(
            franchise_owner_id=owner.id,
            name=bspec["name"],
            sector=bspec["sector"],
            description=bspec["desc"],
            initial_cost=bspec["cost"],
            support_details=f"{DEMO} Açılış eğitimi, operasyon el kitabı, dijital pazarlama.",
            location=bspec["location"],
            is_approved=True,
        )
        db.add(brand)
        db.flush()
    return owner, brand


def _seed_brand_extras(
    db, owner: FranchiseOwner, brand: Brand, *, full: bool = True
) -> None:
    for tname, code, st in [
        (f"{DEMO} Merkez", f"TR-{brand.id}-01", TerritoryStatus.available),
        (f"{DEMO} Bölge 2", f"TR-{brand.id}-02", TerritoryStatus.available),
        (f"{DEMO} Rezerve", f"TR-{brand.id}-03", TerritoryStatus.reserved),
    ]:
        if db.scalar(
            select(BrandTerritory.id).where(
                BrandTerritory.brand_id == brand.id, BrandTerritory.name == tname
            )
        ) is None:
            db.add(
                BrandTerritory(
                    brand_id=brand.id,
                    name=tname,
                    region_code=code,
                    status=st,
                )
            )

    if db.scalar(
        select(FranchiseOutlet.id).where(
            FranchiseOutlet.franchise_owner_id == owner.id,
            FranchiseOutlet.brand_id == brand.id,
        )
    ) is None:
        db.add(
            FranchiseOutlet(
                franchise_owner_id=owner.id,
                brand_id=brand.id,
                name=f"{DEMO} {brand.name[:40]} — Merkez",
                city=owner.city,
                address=f"{owner.city} merkez şube",
                status=OutletStatus.active,
                opened_at=datetime.utcnow() - timedelta(days=300 + brand.id),
            )
        )

    if not full:
        return

    logo_path = _write_placeholder(f"seed/brands/{brand.id}/logo.png")
    if db.scalar(
        select(BrandMedia.id).where(
            BrandMedia.brand_id == brand.id, BrandMedia.media_type == BrandMediaType.logo
        )
    ) is None:
        db.add(
            BrandMedia(
                brand_id=brand.id,
                media_type=BrandMediaType.logo,
                file_path=logo_path,
                mime_type="image/png",
                original_filename="logo.png",
            )
        )

    if db.scalar(
        select(BrandFDDDocument.id).where(
            BrandFDDDocument.brand_id == brand.id,
            BrandFDDDocument.title == f"{DEMO} FDD",
        )
    ) is None:
        db.add(
            BrandFDDDocument(
                brand_id=brand.id,
                title=f"{DEMO} FDD",
                version="2026.1",
                file_path=_write_placeholder(f"seed/brands/{brand.id}/fdd.pdf"),
                mime_type="application/pdf",
                file_size_bytes=1024,
                published_at=datetime.utcnow() - timedelta(days=20),
            )
        )

    if db.scalar(
        select(Inventory.id).where(
            Inventory.franchise_owner_id == owner.id,
            Inventory.item_name == f"{DEMO} Stok — {brand.id}",
        )
    ) is None:
        db.add(
            Inventory(
                franchise_owner_id=owner.id,
                item_name=f"{DEMO} Stok — {brand.id}",
                stock_level=random.randint(20, 200),
                low_stock_threshold=15,
            )
        )

    if db.scalar(
        select(SupplyRequest.id).where(
            SupplyRequest.franchise_owner_id == owner.id,
            SupplyRequest.product_name == f"{DEMO} Tedarik — {brand.id}",
        )
    ) is None:
        db.add(
            SupplyRequest(
                franchise_owner_id=owner.id,
                product_name=f"{DEMO} Tedarik — {brand.id}",
                quantity=random.randint(10, 100),
                status=SupplyRequestStatus.pending,
            )
        )

    if db.scalar(
        select(FranchiseOwnerDocument.id).where(
            FranchiseOwnerDocument.franchise_owner_id == owner.id,
            FranchiseOwnerDocument.title == f"{DEMO} SOP — {brand.id}",
        )
    ) is None:
        db.add(
            FranchiseOwnerDocument(
                franchise_owner_id=owner.id,
                title=f"{DEMO} SOP — {brand.id}",
                document_type=OwnerDocumentType.sop,
                file_path=_write_placeholder(f"seed/owners/{owner.id}/sop_{brand.id}.pdf"),
                mime_type="application/pdf",
                file_size_bytes=512,
            )
        )


def _get_or_create_buyer(db, spec: dict) -> Buyer:
    buyer = db.scalar(select(Buyer).where(Buyer.email == spec["email"]))
    if buyer is None:
        buyer = Buyer(
            email=spec["email"],
            hashed_password=hash_password(PASSWORD_BUYER),
            first_name=spec["first"],
            last_name=spec["last"],
            phone="+9055400" + str(abs(hash(spec["email"])) % 100000).zfill(5),
            city=spec["city"],
            investment_budget=spec["budget"],
            experience_years=spec["exp"],
            preferred_sector=spec["sector"],
            identity_number=f"TR-DEMO-{abs(hash(spec['email'])) % 999999:06d}",
            email_verified=True,
        )
        db.add(buyer)
        db.flush()
    return buyer


def _pick_favorites(buyer_spec: dict, brands: list[Brand], count: int = 5) -> list[Brand]:
    sector = buyer_spec["sector"].lower()
    same = [b for b in brands if b.sector and sector in (b.sector or "").lower()]
    other = [b for b in brands if b not in same]
    picked: list[Brand] = []
    if same:
        picked.extend(random.sample(same, min(len(same), count // 2 + 1)))
    remaining = count - len(picked)
    pool = [b for b in brands if b not in picked]
    if pool and remaining > 0:
        picked.extend(random.sample(pool, min(remaining, len(pool))))
    return picked


def seed(*, num_buyers: int = 30, num_owners: int = 30) -> None:
    owner_specs = generate_owners(num_owners)
    buyer_specs = generate_buyers(num_buyers)

    db = SessionLocal()
    brand_by_name: dict[str, Brand] = {}
    brand_meta: dict[str, dict] = {}
    owner_by_id: dict[int, FranchiseOwner] = {}
    buyer_by_email: dict[str, Buyer] = {}

    try:
        print(f"{DEMO} {num_owners} franchise sahibi + marka...")
        for idx, ospec in enumerate(owner_specs, start=1):
            owner, brand = _get_or_create_owner(db, ospec)
            owner_by_id[owner.id] = owner
            brand_by_name[brand.name] = brand
            brand_meta[brand.name] = {
                "city": ospec["city"],
                "sector": brand.sector,
            }
            _seed_brand_extras(
                db, owner, brand, full=ospec.get("full_extras", idx <= 10)
            )
            if idx % 10 == 0:
                db.commit()
                print(f"  ... {idx}/{num_owners} marka")

        print(f"{DEMO} {num_buyers} alıcı + favoriler...")
        all_brands = list(brand_by_name.values())
        for bspec in buyer_specs:
            buyer = _get_or_create_buyer(db, bspec)
            buyer_by_email[buyer.email] = buyer
            for brand in _pick_favorites(bspec, all_brands, count=random.randint(4, 7)):
                if db.scalar(
                    select(BuyerFavorite.id).where(
                        BuyerFavorite.buyer_id == buyer.id,
                        BuyerFavorite.brand_id == brand.id,
                    )
                ) is None:
                    db.add(BuyerFavorite(buyer_id=buyer.id, brand_id=brand.id))

        brand_names = list(brand_by_name.keys())
        buyer_emails = list(buyer_by_email.keys())
        apps_plan, chat_scripts = generate_applications_and_chats(
            buyer_emails, brand_names, brand_meta
        )

        print(f"{DEMO} {len(apps_plan)} başvuru...")
        app_key_map: dict[tuple[str, str], Application] = {}
        for bem, bname, status_str, note in apps_plan:
            buyer = buyer_by_email[bem]
            brand = brand_by_name[bname]
            status = _STATUS_MAP[status_str]
            notes = f"{DEMO} {note}".strip() if note else f"{DEMO} Başvuru"
            app = db.scalar(
                select(Application).where(
                    Application.buyer_id == buyer.id,
                    Application.brand_id == brand.id,
                )
            )
            if app is None:
                app = Application(
                    buyer_id=buyer.id,
                    brand_id=brand.id,
                    status=status,
                    notes=notes,
                    created_at=datetime.utcnow()
                    - timedelta(days=random.randint(1, 90)),
                )
                db.add(app)
                db.flush()
            else:
                app.status = status
            app_key_map[(bem, bname)] = app

        print(f"{DEMO} {len(chat_scripts)} mesaj thread...")
        for (bem, bname), script in chat_scripts.items():
            app = app_key_map.get((bem, bname))
            if not app or app.status != ApplicationStatus.approved:
                continue
            if db.scalar(select(Message.id).where(Message.application_id == app.id).limit(1)):
                continue
            buyer = buyer_by_email[bem]
            brand = brand_by_name[bname]
            owner = owner_by_id.get(brand.franchise_owner_id)
            if not owner:
                continue
            base_time = datetime.utcnow() - timedelta(days=random.randint(1, 14))
            for i, (who, content) in enumerate(script):
                role = UserRole.buyer if who == "buyer" else UserRole.franchise_owner
                sid = buyer.id if who == "buyer" else owner.id
                db.add(
                    Message(
                        application_id=app.id,
                        sender_role=role,
                        sender_id=sid,
                        content=content,
                        created_at=base_time + timedelta(minutes=i * 12),
                    )
                )

        print(f"{DEMO} Olay bildirimleri (backfill)...")
        from app.notification_events import (
            notify_application_status_change,
            notify_new_application,
            notify_new_message,
        )

        for app in app_key_map.values():
            brand = db.get(Brand, app.brand_id)
            buyer = db.get(Buyer, app.buyer_id)
            if not brand or not buyer:
                continue
            if app.status == ApplicationStatus.pending:
                notify_new_application(
                    db, application=app, brand=brand, buyer=buyer
                )
            else:
                notify_application_status_change(
                    db,
                    application=app,
                    brand=brand,
                    buyer=buyer,
                    new_status=app.status,
                )

        for app in app_key_map.values():
            if app.status != ApplicationStatus.approved:
                continue
            last_msg = db.scalar(
                select(Message)
                .where(Message.application_id == app.id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(1)
            )
            if not last_msg:
                continue
            brand = db.get(Brand, app.brand_id)
            buyer = db.get(Buyer, app.buyer_id)
            if brand and buyer:
                notify_new_message(
                    db,
                    message=last_msg,
                    application=app,
                    brand=brand,
                    buyer=buyer,
                )

        print(f"{DEMO} Push cihaz kayıtları...")
        for buyer in buyer_by_email.values():
            if not db.scalar(
                select(PushDevice.id).where(
                    PushDevice.recipient_role == UserRole.buyer,
                    PushDevice.recipient_id == buyer.id,
                    PushDevice.token == f"demo-{buyer.id}",
                )
            ):
                db.add(
                    PushDevice(
                        recipient_role=UserRole.buyer,
                        recipient_id=buyer.id,
                        token=f"demo-{buyer.id}",
                        platform=DevicePlatform.web,
                    )
                )

        db.commit()

        n_brands = len(brand_by_name)
        n_apps = int(db.scalar(select(func.count(Application.id))) or 0)
        n_msgs = int(db.scalar(select(func.count(Message.id))) or 0)
        n_approved = int(
            db.scalar(
                select(func.count(Application.id)).where(
                    Application.status == ApplicationStatus.approved
                )
            )
            or 0
        )
        n_fav = int(db.scalar(select(func.count(BuyerFavorite.id))) or 0)
        n_notif = int(db.scalar(select(func.count(Notification.id))) or 0)

        print("\n========== DEMO SEED TAMAMLANDI ==========")
        print(
            f"Alıcı: {len(buyer_by_email)} | Sahip: {len(owner_by_id)} | Marka: {n_brands}"
        )
        print(
            f"Başvuru: {n_apps} | Onaylı: {n_approved} | Mesaj: {n_msgs} | "
            f"Favori: {n_fav} | Bildirim: {n_notif}"
        )
        print(f"\nŞifre — alıcı: {PASSWORD_BUYER} | sahip: {PASSWORD_OWNER}")
        print(f"Örnek: buyer1@franchisehub.local | owner.komagene-express@... (slug'a göre)")
        print("\nAgent test:")
        print('  "500 bin TL altı gıda markaları"')
        print('  "İstanbul kahve franchise"')
        print('  "bütçeme uygun Marmara bayilikleri"')
    finally:
        db.close()


def _run_reset() -> None:
    reset_path = ROOT_DIR / "scripts" / "reset_database.py"
    spec = importlib.util.spec_from_file_location("reset_database", reset_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    mod.reset(skip_confirm=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FranchiseHub demo seed")
    parser.add_argument("--reset", action="store_true", help="Önce DB temizle")
    parser.add_argument("--buyers", type=int, default=30, help="Alıcı sayısı (varsayılan 30)")
    parser.add_argument("--owners", type=int, default=30, help="Franchise sahibi/marka sayısı")
    args = parser.parse_args()
    if args.reset:
        _run_reset()
    seed(num_buyers=args.buyers, num_owners=args.owners)

"""
Demo seed: tek buyer, tek franchise_owner, tek admin.
API testleri icin marka, basvurular, mesajlar, envanter, tedarik talepleri doldurulur.
Ayni script birden fazla calistirilabilir (idempotent).
"""
import sys
from pathlib import Path

from sqlalchemy import func, select, text

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import Base, SessionLocal, engine
from app.models import (
    Admin,
    Application,
    ApplicationStatus,
    Brand,
    Buyer,
    FranchiseOwner,
    Inventory,
    Message,
    SupplyRequest,
    SupplyRequestStatus,
    UserRole,
)
from app.security import hash_password

# --- Sabit demo kullanicilar (uc rol) ---
BUYER_EMAIL = "buyer1@franchisehub.local"
BUYER_PASSWORD = "Buyer12345!"

OWNER_EMAIL = "owner1@franchisehub.local"
OWNER_PASSWORD = "Owner12345!"

ADMIN_EMAIL = "admin1@franchisehub.local"
ADMIN_PASSWORD = "Admin12345!"

# Basvuru notlari (tekrar calistirmada ayirt etmek icin)
NOTE_PENDING = "[SEED] Demo basvuru — beklemede"
NOTE_APPROVED = "[SEED] Demo basvuru — onayli (mesajlasma)"
NOTE_REJECTED = "[SEED] Demo basvuru — reddedildi"

# Envanter / tedarik (isimlerle idempotent)
INVENTORY_SEED_ROWS = [
    ("SEED | Espresso makinesi", 4),
    ("SEED | Karton bardak (koli)", 80),
    ("SEED | Sut (lt)", 200),
]

SUPPLY_SEED_ROWS = [
    ("SEED | Kahve cekirdegi (kg)", 25, SupplyRequestStatus.pending),
    ("SEED | Ambalaj malzemesi", 300, SupplyRequestStatus.pending),
    ("SEED | Temizlik urunu seti", 15, SupplyRequestStatus.approved),
]


def _ensure_applications_created_at() -> None:
    """ORM Application.created_at icin kolon; migration calistirilmamissa seed yine calissin."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE applications
                ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW();
                """
            )
        )


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_applications_created_at()
    db = SessionLocal()
    try:
        # --- 1) Buyer ---
        buyer = db.scalar(select(Buyer).where(Buyer.email == BUYER_EMAIL))
        if buyer is None:
            buyer = Buyer(
                email=BUYER_EMAIL,
                hashed_password=hash_password(BUYER_PASSWORD),
                first_name="Ayse",
                last_name="Demir",
                phone="+905550001111",
                city="Istanbul",
                investment_budget=3_500_000,
                experience_years=3,
                preferred_sector="Kafe",
                identity_number="TR-SEED-BUYER-001",
            )
            db.add(buyer)
        db.flush()

        # --- 2) Franchise owner ---
        owner = db.scalar(select(FranchiseOwner).where(FranchiseOwner.email == OWNER_EMAIL))
        if owner is None:
            owner = FranchiseOwner(
                email=OWNER_EMAIL,
                hashed_password=hash_password(OWNER_PASSWORD),
                company_name="Demo Franchise A.S.",
                tax_number="TAX-SEED-2026-001",
                phone="+905550002222",
                authorized_person_name="Mehmet Kaya",
                country="Turkiye",
                city="Istanbul",
                company_address="Maslak Mah. Buyukdere Cad. No:1, Istanbul",
                website="https://demo-franchise.local",
                verification_status=True,
            )
            db.add(owner)
        db.flush()

        # --- 3) Admin ---
        admin = db.scalar(select(Admin).where(Admin.email == ADMIN_EMAIL))
        if admin is None:
            admin = Admin(
                email=ADMIN_EMAIL,
                hashed_password=hash_password(ADMIN_PASSWORD),
                full_name="Platform Admin (Seed)",
                phone="+905550003333",
                authorization_level="supervisor",
                is_superadmin=True,
            )
            db.add(admin)

        # --- 4) Marka (owner’a bagli, buyer listesinde gorunsun) ---
        brand = db.scalar(select(Brand).where(Brand.franchise_owner_id == owner.id))
        if brand is None:
            brand = Brand(
                franchise_owner_id=owner.id,
                name="Demo Kahve Franchise",
                sector="Kafe",
                description="Seed marka: franchise sahibi paneli, basvuru ve envanter API testleri.",
                initial_cost=2_500_000,
                support_details="Acilis egitimi, 12 ay saha destegi, CRM erisimi.",
                location="Istanbul, Ankara, Izmir",
                is_approved=True,
            )
            db.add(brand)
            db.flush()
        else:
            # Eksik alanlari tamamla (mevcut seed DB icin)
            brand.franchise_owner_id = owner.id
            brand.is_approved = True
            if not brand.description:
                brand.description = "Seed marka: franchise sahibi paneli, basvuru ve envanter API testleri."
            if brand.initial_cost is None or brand.initial_cost <= 0:
                brand.initial_cost = 2_500_000

        db.flush()

        # --- 5) Basvurular (pending / approved / rejected) ---
        def ensure_application(
            notes: str, status: ApplicationStatus
        ) -> Application:
            app = db.scalar(
                select(Application).where(
                    Application.buyer_id == buyer.id,
                    Application.brand_id == brand.id,
                    Application.notes == notes,
                )
            )
            if app:
                if app.status != status:
                    app.status = status
                return app
            app = Application(
                buyer_id=buyer.id,
                brand_id=brand.id,
                status=status,
                notes=notes,
            )
            db.add(app)
            db.flush()
            return app

        app_pending = ensure_application(NOTE_PENDING, ApplicationStatus.pending)
        app_approved = ensure_application(NOTE_APPROVED, ApplicationStatus.approved)
        app_rejected = ensure_application(NOTE_REJECTED, ApplicationStatus.rejected)

        # --- 6) Mesajlar (sadece onayli basvuru) ---
        msg_count = db.scalar(
            select(func.count(Message.id)).where(
                Message.application_id == app_approved.id
            )
        ) or 0
        if msg_count == 0:
            db.add(
                Message(
                    application_id=app_approved.id,
                    sender_role=UserRole.buyer,
                    sender_id=buyer.id,
                    content="[SEED] Merhaba, Kadikoy subesi icin gorusmek isterim.",
                )
            )
            db.add(
                Message(
                    application_id=app_approved.id,
                    sender_role=UserRole.franchise_owner,
                    sender_id=owner.id,
                    content="[SEED] Merhaba Ayse Hanim, bu hafta uygun oldugunuz bir gun iletelim.",
                )
            )

        # --- 7) Envanter ---
        for item_name, stock in INVENTORY_SEED_ROWS:
            inv = db.scalar(
                select(Inventory).where(
                    Inventory.franchise_owner_id == owner.id,
                    Inventory.item_name == item_name,
                )
            )
            if inv is None:
                db.add(
                    Inventory(
                        franchise_owner_id=owner.id,
                        item_name=item_name,
                        stock_level=stock,
                    )
                )
            else:
                inv.stock_level = stock

        # --- 8) Tedarik talepleri ---
        for product_name, quantity, st in SUPPLY_SEED_ROWS:
            sr = db.scalar(
                select(SupplyRequest).where(
                    SupplyRequest.franchise_owner_id == owner.id,
                    SupplyRequest.product_name == product_name,
                )
            )
            if sr is None:
                db.add(
                    SupplyRequest(
                        franchise_owner_id=owner.id,
                        product_name=product_name,
                        quantity=quantity,
                        status=st,
                    )
                )
            else:
                sr.quantity = quantity
                sr.status = st

        db.commit()

        # Ozet
        n_apps = db.scalar(
            select(func.count(Application.id)).where(Application.brand_id == brand.id)
        )
        n_msg = db.scalar(
            select(func.count(Message.id)).where(Message.application_id == app_approved.id)
        )
        n_inv = db.scalar(
            select(func.count(Inventory.id)).where(
                Inventory.franchise_owner_id == owner.id
            )
        )
        n_sr = db.scalar(
            select(func.count(SupplyRequest.id)).where(
                SupplyRequest.franchise_owner_id == owner.id
            )
        )

        print("=== Seed tamamlandi (3 kullanici + tam demo veri) ===")
        print(f"Buyer:     {BUYER_EMAIL} / {BUYER_PASSWORD}")
        print(f"Owner:     {OWNER_EMAIL} / {OWNER_PASSWORD}")
        print(f"Admin:     {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
        print(f"Marka:     id={brand.id} {brand.name!r} (onayli={brand.is_approved})")
        print(f"Basvurular: pending id={app_pending.id}, approved id={app_approved.id}, rejected id={app_rejected.id} (toplam markaya: {n_apps})")
        print(f"Mesajlar (onayli basvuru): {n_msg}")
        print(f"Envanter kalemi: {n_inv}")
        print(f"Tedarik talebi: {n_sr}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()

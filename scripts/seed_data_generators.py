"""Programatik demo veri uretici — seed_test_users.py tarafindan kullanilir."""
from __future__ import annotations

import random
from typing import Any

random.seed(42)

SECTORS = ["Gıda", "Kahve", "Güzellik", "Perakende", "Eğitim", "Sağlık", "Hizmet", "Otomotiv"]
CITIES = [
    "İstanbul",
    "Ankara",
    "İzmir",
    "Bursa",
    "Antalya",
    "Adana",
    "Konya",
    "Gaziantep",
    "Kocaeli",
    "Mersin",
    "Eskişehir",
    "Trabzon",
]
FIRST_NAMES = [
    "Ayşe", "Mehmet", "Zeynep", "Can", "Elif", "Murat", "Selin", "Burak", "Deniz",
    "Fatma", "Ahmet", "Ece", "Kaan", "Merve", "Oğuz", "Pınar", "Serkan", "Ceren",
    "Emre", "Gamze", "Hakan", "İrem", "Tolga", "Yasemin", "Barış", "Dilara",
]
LAST_NAMES = [
    "Yılmaz", "Kaya", "Demir", "Çelik", "Şahin", "Yıldız", "Aydın", "Öztürk",
    "Arslan", "Koç", "Polat", "Aktaş", "Erdoğan", "Kurt", "Özkan", "Aslan",
    "Doğan", "Güneş", "Aksoy", "Tekin",
]
BRAND_STEMS = [
    ("Komagene", "Gıda", 350_000, 550_000),
    ("Brew", "Kahve", 300_000, 900_000),
    ("Burger", "Gıda", 800_000, 1_500_000),
    ("Pizza", "Gıda", 600_000, 1_200_000),
    ("Market", "Perakende", 500_000, 1_000_000),
    ("Studio", "Güzellik", 400_000, 800_000),
    ("Edu", "Eğitim", 450_000, 950_000),
    ("Fit", "Sağlık", 550_000, 1_100_000),
    ("Clean", "Hizmet", 250_000, 600_000),
    ("Auto", "Otomotiv", 700_000, 2_000_000),
    ("Döner", "Gıda", 280_000, 500_000),
    ("Waffle", "Gıda", 320_000, 650_000),
    ("Kafe", "Kahve", 380_000, 750_000),
    ("Kuaför", "Güzellik", 420_000, 700_000),
    ("STEM", "Eğitim", 500_000, 1_300_000),
]
SUFFIXES = ["Express", "Plus", "Pro", "Hub", "Point", "Zone", "Max", "TR", "City", "Line"]


def _slug(s: str) -> str:
    return (
        s.lower()
        .replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
        .replace(" ", "-")
    )


def generate_owners(count: int) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    used_names: set[str] = set()
    for i in range(1, count + 1):
        stem, sector, lo, hi = BRAND_STEMS[(i - 1) % len(BRAND_STEMS)]
        suffix = SUFFIXES[(i * 3) % len(SUFFIXES)]
        brand_name = f"{stem} {suffix}"
        n = 1
        while brand_name in used_names:
            n += 1
            brand_name = f"{stem} {suffix} {n}"
        used_names.add(brand_name)

        city = CITIES[(i - 1) % len(CITIES)]
        city2 = CITIES[(i + 3) % len(CITIES)]
        person = f"{FIRST_NAMES[i % len(FIRST_NAMES)]} {LAST_NAMES[(i * 2) % len(LAST_NAMES)]}"
        cost = float(random.randint(lo // 50_000, hi // 50_000) * 50_000)
        slug = _slug(brand_name)

        specs.append(
            {
                "email": f"owner.{slug}@franchisehub.local",
                "company": f"{brand_name} Franchise A.Ş.",
                "tax": f"TAX-SEED-{i:04d}",
                "person": person,
                "city": city,
                "brand": {
                    "name": brand_name,
                    "sector": sector,
                    "cost": cost,
                    "location": f"{city}, {city2}",
                    "desc": f"{brand_name} — {sector} sektöründe franchise fırsatı. {city} ve çevresi.",
                },
                "full_extras": i <= 10,
            }
        )
    return specs


def generate_buyers(count: int) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for i in range(1, count + 1):
        sector = SECTORS[(i - 1) % len(SECTORS)]
        city = CITIES[(i * 2) % len(CITIES)]
        budget = float(random.choice([400_000, 600_000, 800_000, 1_000_000, 1_500_000, 2_000_000, 2_500_000, 3_500_000]))
        specs.append(
            {
                "email": f"buyer{i}@franchisehub.local",
                "first": FIRST_NAMES[(i + 5) % len(FIRST_NAMES)],
                "last": LAST_NAMES[(i + 7) % len(LAST_NAMES)],
                "city": city,
                "budget": budget,
                "sector": sector,
                "exp": (i % 12) + 1,
            }
        )
    return specs


def pick_favorites(buyer_spec: dict, brand_names: list[str], count: int = 5) -> list[str]:
    sector = buyer_spec["sector"]
    same = [n for n in brand_names if sector.lower() in n.lower() or True]
    # sector match via brand data — pass brands list instead
    return random.sample(brand_names, min(count, len(brand_names)))


def generate_applications_and_chats(
    buyer_emails: list[str],
    brand_names: list[str],
    brand_meta: dict[str, dict],
) -> tuple[
    list[tuple[str, str, str, str]],
    dict[tuple[str, str], list[tuple[str, str]]],
]:
    """Returns (applications_plan, chat_scripts). status is str enum value."""
    apps: list[tuple[str, str, str, str]] = []
    chats: dict[tuple[str, str], list[tuple[str, str]]] = {}

    for bem in buyer_emails:
        n = random.randint(3, 7)
        chosen = random.sample(brand_names, min(n, len(brand_names)))
        for bname in chosen:
            roll = random.random()
            if roll < 0.38:
                status = "approved"
            elif roll < 0.72:
                status = "pending"
            else:
                status = "rejected"
            note = f"{random.choice(['Lokasyon araştırması', 'Bütçe değerlendirmesi', 'İlk görüşme talebi', 'Bölge analizi', ''])}"
            apps.append((bem, bname, status, note))

            if status == "approved" and random.random() < 0.85:
                meta = brand_meta.get(bname, {})
                city = meta.get("city", "şehir")
                msgs = [
                    ("buyer", f"Merhaba, {bname} için {city} bölgesinde bilgi alabilir miyim?"),
                    ("owner", f"Merhaba, {bname} franchise şartlarımızı paylaşabiliriz. Randevu uygun mu?"),
                    ("buyer", random.choice(["Evet, bu hafta uygun.", "Ön bilgi formu gönderebilir misiniz?", "Bütçe aralığını netleştirelim."])),
                ]
                if random.random() > 0.4:
                    msgs.append(
                        (
                            "owner",
                            random.choice(
                                [
                                    "FDD özetini ilettik, incelemenizi bekliyoruz.",
                                    "Lokasyon listesi ektedir.",
                                    "ROI projeksiyonu metrics sayfasında.",
                                ]
                            ),
                        )
                    )
                chats[(bem, bname)] = msgs

    return apps, chats

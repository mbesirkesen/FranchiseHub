from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from .models import Buyer
from .region_filters import REGION_LABELS

# Frontend agent-query-parser ile uyumlu sektör eşlemeleri
SECTOR_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("fast-food", "fast food", "fastfood", "burger", "hamburger"), "Gıda"),
    (("gıda", "gida", "restoran", "yemek", "bayilik"), "Gıda"),
    (("kahve", "cafe", "kafe", "coffee"), "Kahve"),
    # DB'de sektör "Kafe" yazan markalar için
    (("kafe",), "Kafe"),
    (("güzellik", "guzellik", "kuaför", "kuafor", "güzellik"), "Güzellik"),
    (("perakende", "mağaza", "magaza", "retail"), "Perakende"),
]

REGION_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("marmara",), "marmara"),
    (("ege",), "ege"),
    (("akdeniz",), "akdeniz"),
    (("iç anadolu", "ic anadolu", "icanadolu", "içanadolu"), "icanadolu"),
    (("karadeniz",), "karadeniz"),
    (("doğu anadolu", "dogu anadolu", "doğu", "dogu"), "dogu"),
    (("güneydoğu", "guneydogu"), "guneydogu"),
]

CITY_KEYWORDS: dict[str, str] = {
    "istanbul": "İstanbul",
    "ankara": "Ankara",
    "izmir": "İzmir",
    "bursa": "Bursa",
    "antalya": "Antalya",
}

COMPARE_HINTS = ("karşılaştır", "karsilastir", "compare")
DETAIL_HINTS = ("roi", "getiri", "trend", "şube", "sube", "metrik", "kaç şube", "büyüme")
APPLICATION_HINTS = ("başvuru", "basvuru", "application", "başvurum", "basvurum", "durumda", "başvurularım", "basvurularim")
GENERAL_HINTS = ("franchise nedir", "bayilik nedir", "nasıl çalışır", "nasil calisir")
GREETING_HINTS = ("merhaba", "selam", "naber", "gunaydin", "günaydın", "iyi gunler", "iyi günler", "nasilsin", "nasılsın")
HELP_HINTS = ("yardim", "yardım", "nasil kullanilir", "nasıl kullanılır", "ne yapabilirsin")
RECOMMEND_HINTS = ("onerir", "önerir", "tavsiye", "ne onerirsin", "ne önerirsin", "bana uygun", "uygun marka", "öneri", "oneri")
PRODUCT_KEYWORDS = ("pizza", "doner", "döner", "burger", "waffle", "tatli", "tatlı", "cicek", "çiçek", "komagene", "starbucks", "brew")
BRAND_INFO_HINTS = ("hakkinda", "hakkında", "detay", "bilgi ver", "nedir bu")
FAVORITES_HINTS = ("favori", "favorilerim", "favorilerime", "favorilerimde")
EXCLUDE_APPLIED_HINTS = (
    "basvurdugum haric",
    "başvurduğum hariç",
    "daha once basvur",
    "daha önce başvur",
    "basvurmadigim",
    "başvurmadığım",
)
TERRITORY_HINTS = ("müsait bölge", "musait bolge", "territory", "bölge var mı", "bolge var mi", "müsaitlik")
GIBBERISH_MIN_ALPHA = 3
# classify_intent ile belirlenen niyetler gibberish ile ezilmemeli
GIBBERISH_EXEMPT_INTENTS = frozenset(
    {
        "application_status",
        "brand_compare",
        "favorites_similar",
        "general",
        "brand_detail",
        "territory_check",
    }
)
REFINE_HINTS = (
    "daha ucuz",
    "daha pahali",
    "daha pahalı",
    "daha az",
    "daha cok",
    "daha çok",
    "daha uygun",
    "bunlar",
    "bunların",
    "bunlarin",
    "aynı",
    "ayni",
    "devam",
    "baska",
    "başka",
    "peki ya",
    "peki",
    "onun yerine",
    "bunun disinda",
    "bunun dışında",
    "goster",
    "göster",
    "olsun",
    "degil",
    "değil",
    "sektor",
    "sektör",
    "yerine",
    "baska sektor",
    "başka sektör",
    "en ucuz",
    "en ucuzu",
    "en pahali",
    "en pahalı",
    "en ucuza",
    "hangisi",
    "hangisini",
    "en iyi",
    "en uygun",
)


@dataclass
class AgentSearchFilters:
    sector: Optional[str] = None
    location: Optional[str] = None
    region: Optional[str] = None
    min_cost: Optional[float] = None
    max_cost: Optional[float] = None
    q: Optional[str] = None
    use_profile_budget: bool = False
    use_profile_sector: bool = False
    use_profile_city: bool = False
    sort: str = "cost_asc"
    exclude_applied: bool = False
    similar_to_favorites: bool = False


@dataclass
class AgentNluResult:
    intent: str
    filters: AgentSearchFilters = field(default_factory=AgentSearchFilters)
    free_text_tokens: list[str] = field(default_factory=list)
    compare_brand_names: list[str] = field(default_factory=list)
    pick_mode: Optional[str] = None  # cheapest | expensive | best_match


def _normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower().replace("'", "'").replace("'", "'")
    return (
        t.replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )


def _parse_money_tl(text: str) -> tuple[Optional[float], Optional[float]]:
    """(min_cost, max_cost) — altı/üstü ifadelerine göre."""
    norm = _normalize(text)
    min_cost: Optional[float] = None
    max_cost: Optional[float] = None

    def _amount_from_match(num_str: str, unit: str) -> float:
        num = float(num_str.replace(",", "."))
        if unit in ("milyon", "m"):
            return num * 1_000_000
        if unit in ("bin", "k"):
            return num * 1_000
        return num

    patterns = [
        r"(\d+(?:[.,]\d+)?)\s*(milyon|m)\b",
        r"(\d+(?:[.,]\d+)?)\s*(bin|k)\b",
        r"(\d+(?:[.,]\d+)?)\s*tl\b",
    ]
    amounts: list[tuple[float, str]] = []
    for pat in patterns:
        for m in re.finditer(pat, norm):
            unit = m.group(2) if m.lastindex and m.lastindex >= 2 else ""
            amounts.append((_amount_from_match(m.group(1), unit), m.group(0)))

    if not amounts and re.search(r"\b(\d{4,7})\b", norm):
        for m in re.finditer(r"\b(\d{4,7})\b", norm):
            amounts.append((float(m.group(1)), m.group(0)))

    for value, fragment in amounts:
        if any(w in fragment for w in ("alti", "altı", "under", "kadar", "max")) or any(
            w in norm for w in ("alti", "altı", "kadar", "under", "max")
        ):
            max_cost = value if max_cost is None else min(max_cost, value)
        elif any(w in norm for w in ("ustu", "üstü", "min", "en az")):
            min_cost = value if min_cost is None else max(min_cost, value)
        else:
            max_cost = value if max_cost is None else min(max_cost, value)

    if re.search(r"butceme|bütçeme|butcem|bütçem", norm):
        return None, None  # profil bütçesi — caller işler

    return min_cost, max_cost


def _detect_sector(norm: str) -> Optional[str]:
    for keywords, sector in SECTOR_KEYWORDS:
        if any(kw in norm for kw in keywords):
            return sector
    return None


def _detect_region(norm: str) -> Optional[str]:
    for keywords, key in REGION_KEYWORDS:
        if any(kw in norm for kw in keywords):
            return key
    return None


def _detect_city(norm: str) -> Optional[str]:
    for key, label in CITY_KEYWORDS.items():
        if key in norm:
            return label
    return None


def _is_compare_intent(norm: str, raw: str) -> bool:
    if any(h in norm for h in COMPARE_HINTS) or " vs " in norm:
        return True
    # «Komagene ile Brew Max» — yalnızca karşılaştırma fiili veya iki marka adı
    if re.search(r"\s+ile\s+", norm) and not re.search(
        r"ne yapabilirim|ne yapabilir|nasil|nasıl|yapmak|istiyorum", norm
    ):
        names = extract_compare_brand_names(raw)
        if len(names) >= 2:
            return True
    return False


def _is_gibberish(norm: str) -> bool:
    if any(h in norm for h in APPLICATION_HINTS + COMPARE_HINTS + FAVORITES_HINTS + GENERAL_HINTS):
        return False
    if any(h in norm for h in GREETING_HINTS + HELP_HINTS + RECOMMEND_HINTS + PRODUCT_KEYWORDS):
        return False
    if any(h in norm for h in REFINE_HINTS):
        return False
    letters = re.sub(r"[^a-z]", "", norm)
    if len(letters) < GIBBERISH_MIN_ALPHA:
        return True
    known = set()
    for kws, _ in SECTOR_KEYWORDS + REGION_KEYWORDS:
        known.update(kws)
    known.update(CITY_KEYWORDS.keys())
    known.update(
        "butceme butce bütçe marmara gıda kahve franchise bayilik marka roi alti altı".split()
    )
    if any(k in norm for k in known):
        return False
    if re.search(r"\d+\s*(bin|k|milyon|tl)|butce|bütç", norm):
        return False
    if len(letters) <= 14:
        return True
    return not any(w in norm for w in ("franchise", "bayilik", "marka"))


def extract_compare_brand_names(query: str) -> list[str]:
    norm = _normalize(query)
    for token in ("karsilastir", "karşılaştır", "compare", "markalari", "markaları"):
        norm = norm.replace(token, " ")
    parts = re.split(r"\s+(?:ile|ve|vs|veya)\s+", norm)
    names: list[str] = []
    for part in parts:
        cleaned = re.sub(r"[^a-z0-9\s]", " ", part).strip()
        if len(cleaned) < 3:
            continue
        # Çok genel kelimeleri at
        if cleaned in ("marka", "franchise", "bayilik", "hangisi", "daha", "iyi"):
            continue
        title = " ".join(w.capitalize() for w in cleaned.split())
        if title and title not in names:
            names.append(title)
    return names[:4]


def classify_intent(query: str, brand_id: Optional[int]) -> str:
    norm = _normalize(query)
    if brand_id is not None and any(h in norm for h in TERRITORY_HINTS):
        return "territory_check"
    if brand_id is not None and any(h in norm for h in DETAIL_HINTS):
        return "brand_detail"
    if any(h in norm for h in APPLICATION_HINTS):
        return "application_status"
    if any(h in norm for h in FAVORITES_HINTS) and any(
        w in norm for w in ("benzer", "oner", "öner", "gibi", "similar")
    ):
        return "favorites_similar"
    if _is_compare_intent(norm, query):
        return "brand_compare"
    if any(h in norm for h in GENERAL_HINTS):
        return "general"
    if any(norm == g or norm.startswith(g + " ") for g in GREETING_HINTS + HELP_HINTS):
        return "general"
    if any(h in norm for h in RECOMMEND_HINTS):
        return "brand_search"
    if any(p in norm for p in PRODUCT_KEYWORDS):
        return "brand_search"
    if any(h in norm for h in BRAND_INFO_HINTS):
        return "brand_search"
    if _is_gibberish(norm):
        return "no_match"
    has_money = bool(
        re.search(r"\d+\s*(bin|k|milyon|m\b|tl\b)", norm)
        or re.search(r"\b\d{4,9}\b", norm)
        or "butce" in norm
        or "bütç" in norm
    )
    if (
        _detect_sector(norm)
        or _detect_region(norm)
        or _detect_city(norm)
        or has_money
        or "franchise" in norm
        or "bayilik" in norm
        or "marka" in norm
    ):
        return "brand_search"
    return "no_match"


def _filters_from_applied(data: Optional[dict]) -> AgentSearchFilters:
    if not data:
        return AgentSearchFilters()
    f = AgentSearchFilters()
    if data.get("sector"):
        f.sector = str(data["sector"])
    if data.get("location"):
        f.location = str(data["location"])
    if data.get("region"):
        f.region = str(data["region"])
    if data.get("min_cost") is not None:
        f.min_cost = float(data["min_cost"])
    if data.get("max_cost") is not None:
        f.max_cost = float(data["max_cost"])
    if data.get("q"):
        f.q = str(data["q"])
    if data.get("use_profile_budget"):
        f.use_profile_budget = True
    if data.get("use_profile_sector"):
        f.use_profile_sector = True
    if data.get("use_profile_city"):
        f.use_profile_city = True
    if data.get("exclude_applied"):
        f.exclude_applied = True
    if data.get("sort"):
        f.sort = str(data["sort"])
    return f


def _detect_pick_mode(norm: str) -> Optional[str]:
    """Önceki listeden seçim: en ucuz hangisi, en iyisi vb."""
    if re.search(r"en ucuz|en ucuzu|en ucuza|en dusuk|en düşük", norm):
        return "cheapest"
    if re.search(r"hangisi", norm) and re.search(r"ucuz", norm):
        return "cheapest"
    if re.search(r"en pahali|en pahalı|en yuksek|en yüksek", norm):
        return "expensive"
    if re.search(r"hangisi", norm) and re.search(r"pahali|pahalı", norm):
        return "expensive"
    if re.search(r"en iyi|en uygun|hangisi iyi|hangisi daha iyi", norm):
        return "best_match"
    if norm.strip() in ("hangisi", "hangisini", "en iyisi", "en ucuzu"):
        return "cheapest" if "ucuz" in norm else "best_match"
    if re.search(r"^hangisi\b", norm):
        return "cheapest"
    return None


def _is_refine_follow_up(norm: str) -> bool:
    return any(h in norm for h in REFINE_HINTS) or _detect_pick_mode(norm) is not None


def _is_context_follow_up(norm: str, previous_search: Optional[dict]) -> bool:
    """Önceki aramaya bağlı kısa takip sorusu (sektör/şehir değişimi dahil)."""
    if not previous_search:
        return False
    if _is_refine_follow_up(norm):
        return True
    if len(norm.split()) > 8:
        return False
    return bool(_detect_sector(norm) or _detect_city(norm) or _detect_region(norm))


def _merge_query_overrides(filters: AgentSearchFilters, norm: str) -> None:
    sector = _detect_sector(norm)
    if sector:
        filters.sector = sector
        filters.use_profile_sector = False
    city = _detect_city(norm)
    if city:
        filters.location = city
        filters.use_profile_city = False
    region = _detect_region(norm)
    if region:
        filters.region = region
    min_parsed, max_parsed = _parse_money_tl(norm)
    if min_parsed is not None:
        filters.min_cost = min_parsed
    if max_parsed is not None:
        filters.max_cost = max_parsed
        filters.use_profile_budget = False


def _apply_conversational_filters(filters: AgentSearchFilters, norm: str, buyer: Buyer) -> None:
    if re.search(r"\bucuz\b", norm):
        filters.sort = "cost_asc"
        if filters.q in ("ucuz", "ucuzlar", "ucuza"):
            filters.q = None
    elif re.search(r"\bpahali|pahalı|premium|luks|lüks\b", norm):
        filters.sort = "cost_desc"
    if re.search(r"\biyi\b|en iyi|roi|getiri", norm):
        filters.sort = "cost_desc"
    if re.search(
        r"butceme|bütçeme|butcem|bütçem|butceme gore|bütçeme göre|oner|öner|tavsiye|bana uygun|uygun marka",
        norm,
    ):
        filters.use_profile_budget = True
        filters.max_cost = float(buyer.investment_budget)
    for product in PRODUCT_KEYWORDS:
        if product in norm and not filters.q:
            filters.q = product
            break
    if filters.location and filters.q and filters.q in CITY_KEYWORDS:
        filters.q = None


def extract_brand_name_tokens(norm: str) -> list[str]:
    stop = {
        "hakkinda", "hakkında", "bilgi", "detay", "nedir", "marka", "franchise",
        "bayilik", "icin", "için", "ver", "lutfen", "lütfen",
    }
    tokens = [t for t in re.split(r"\s+", norm) if len(t) >= 3 and t not in stop]
    return [" ".join(w.capitalize() for w in t.split()) for t in tokens[:4]]


def _apply_refine_to_filters(filters: AgentSearchFilters, norm: str, buyer: Buyer) -> None:
    if re.search(r"daha ucuz|daha az|daha uygun", norm):
        filters.sort = "cost_asc"
        if filters.max_cost is not None:
            filters.max_cost = filters.max_cost * 0.85
        elif filters.use_profile_budget:
            filters.max_cost = float(buyer.investment_budget) * 0.85
    elif re.search(r"daha pahali|daha pahalı|daha cok|daha çok", norm):
        filters.sort = "cost_desc"
        if filters.max_cost is not None:
            filters.min_cost = filters.max_cost * 0.9
            filters.max_cost = None
    if re.search(r"butceme|bütçeme|butcem|bütçem", norm):
        filters.use_profile_budget = True
        filters.max_cost = float(buyer.investment_budget)


def parse_agent_query(
    query: str,
    buyer: Buyer,
    *,
    previous_search: Optional[dict] = None,
) -> AgentNluResult:
    raw = query.strip()
    norm = _normalize(raw)
    intent = classify_intent(raw, None)

    filters = AgentSearchFilters()
    filters.sector = _detect_sector(norm)
    filters.region = _detect_region(norm)
    filters.location = _detect_city(norm)

    min_parsed, max_parsed = _parse_money_tl(raw)
    if re.search(r"butceme|bütçeme|butcem|bütçem", norm):
        filters.use_profile_budget = True
        filters.max_cost = float(buyer.investment_budget)
    else:
        filters.min_cost = min_parsed
        filters.max_cost = max_parsed

    # Serbest metin: sektör/bölge dışı kısa anahtar kelimeler
    tokens = [t for t in re.split(r"\s+", norm) if len(t) >= 3]
    stop = {
        "marka", "markalari", "markalar", "franchise", "bayilik", "bayilikleri",
        "icin", "için", "alti", "altı", "uygun", "firsat", "fırsat", "lari", "ler",
        "bin", "milyon", "tl", "kadar", "butceme", "butcem", "butce", "bana", "sana",
        "onerir", "önerir", "onerirsin", "önerirsin", "oner", "öner", "misin", "mısın",
        "iyi", "hangi", "en",
        "var", "mi", "mı", "ne", "nasil", "nasıl", "istiyorum", "kurmak", "is", "iş",
        "yapabilirim", "yapabilir", "ile", "ve", "olsun", "goster", "göster", "peki", "ya", "bir", "the",
        "hakkinda", "hakkında", "bilgi", "detay", "yardim", "yardım", "et", "selam",
        "merhaba", "tavsiye", "oneri", "öneri", "gore", "göre",
    }
    free = [t for t in tokens if t not in stop and not t.isdigit()]
    if free and not filters.q:
        short = [
            t for t in free
            if 3 <= len(t) <= 12 and t not in ("gida", "gıda", "marmara", "istanbulda", "ankarada")
        ]
        if short:
            filters.q = short[0]
    if filters.location and filters.q:
        filters.q = None

    compare_names: list[str] = []
    if intent == "brand_compare":
        compare_names = extract_compare_brand_names(raw)

    if any(h in norm for h in EXCLUDE_APPLIED_HINTS):
        filters.exclude_applied = True

    if _is_gibberish(norm) and intent not in GIBBERISH_EXEMPT_INTENTS:
        intent = "no_match"

    pick_mode = _detect_pick_mode(norm)
    if pick_mode and previous_search:
        prev_ids = previous_search.get("related_brand_ids") or []
        if prev_ids:
            intent = "brand_pick"
            prev_filters = previous_search.get("filters_applied")
            if isinstance(prev_filters, dict):
                filters = _filters_from_applied(prev_filters)

    if intent == "no_match" and _is_context_follow_up(norm, previous_search):
        prev_filters = previous_search.get("filters_applied") if previous_search else None
        if isinstance(prev_filters, dict) and prev_filters:
            intent = "brand_search"
            filters = _filters_from_applied(prev_filters)
            _apply_refine_to_filters(filters, norm, buyer)
            _merge_query_overrides(filters, norm)

    # Profil varsayılanları — yalnızca anlamlı brand_search sorgularında
    if intent == "brand_search":
        _apply_conversational_filters(filters, norm, buyer)
        if filters.max_cost is None and filters.use_profile_budget:
            filters.max_cost = float(buyer.investment_budget)
        if filters.sector is None and (
            filters.use_profile_budget
            or re.search(
                r"butceme|bütçeme|öner|oner|uygun|tavsiye|bana uygun|ne onerirsin|ne önerirsin",
                norm,
            )
        ):
            if buyer.preferred_sector:
                filters.use_profile_sector = True
                filters.sector = buyer.preferred_sector
        if filters.location is None and filters.region is None and buyer.city:
            if re.search(r"yakın|yakin|yakınımda|sehrim|şehrim|is kurmak|iş kurmak", norm):
                filters.use_profile_city = True
                filters.location = buyer.city
        if (
            filters.sector is None
            and filters.max_cost is None
            and not filters.q
            and any(h in norm for h in RECOMMEND_HINTS)
        ):
            filters.use_profile_budget = True
            filters.max_cost = float(buyer.investment_budget)
            if buyer.preferred_sector:
                filters.use_profile_sector = True
                filters.sector = buyer.preferred_sector
        if filters.max_cost is not None and re.search(r"ne yapabilirim|ne yapabilir", norm):
            if filters.q in ("ile", "ve", "ne"):
                filters.q = None
            if buyer.preferred_sector and filters.sector is None:
                filters.sector = buyer.preferred_sector
                filters.use_profile_sector = True

    return AgentNluResult(
        intent=intent,
        filters=filters,
        free_text_tokens=free,
        compare_brand_names=compare_names,
        pick_mode=pick_mode if intent == "brand_pick" else None,
    )


def filters_applied_dict(filters: AgentSearchFilters) -> dict[str, object]:
    out: dict[str, object] = {"sort": filters.sort}
    if filters.sector:
        out["sector"] = filters.sector
    if filters.location:
        out["location"] = filters.location
    if filters.region:
        out["region"] = filters.region
    if filters.min_cost is not None:
        out["min_cost"] = filters.min_cost
    if filters.max_cost is not None:
        out["max_cost"] = filters.max_cost
    if filters.q:
        out["q"] = filters.q
    if filters.use_profile_budget:
        out["use_profile_budget"] = True
    if filters.use_profile_sector:
        out["use_profile_sector"] = True
    if filters.exclude_applied:
        out["exclude_applied"] = True
    if filters.similar_to_favorites:
        out["similar_to_favorites"] = True
    return out


def filters_human_label(filters: AgentSearchFilters, profile_budget: float) -> str:
    parts: list[str] = []
    if filters.sector:
        parts.append(filters.sector)
    if filters.region:
        parts.append(REGION_LABELS.get(filters.region, filters.region))
    if filters.location:
        parts.append(filters.location)
    if filters.max_cost is not None:
        if filters.use_profile_budget:
            parts.append(f"Profilinizdeki {profile_budget:,.0f} TL bütçe")
        else:
            parts.append(f"{filters.max_cost:,.0f} TL altı")
    if filters.min_cost is not None:
        parts.append(f"{filters.min_cost:,.0f} TL üstü")
    if filters.q:
        parts.append(f"«{filters.q}»")
    return " · ".join(parts) if parts else "genel arama"

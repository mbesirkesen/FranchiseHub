from __future__ import annotations

# Türkiye bölge alias'ları — GET /brands?region=marmara vb.
REGION_LABELS: dict[str, str] = {
    "marmara": "Marmara",
    "ege": "Ege",
    "akdeniz": "Akdeniz",
    "icanadolu": "İç Anadolu",
    "karadeniz": "Karadeniz",
    "dogu": "Doğu Anadolu",
    "guneydogu": "Güneydoğu Anadolu",
}

REGION_ALIASES: dict[str, list[str]] = {
    "marmara": ["istanbul", "bursa", "kocaeli", "tekirdag", "tekirdağ", "sakarya", "tr-34", "tr-16"],
    "ege": ["izmir", "aydin", "aydın", "manisa", "mugla", "muğla", "denizli", "tr-35", "tr-09"],
    "akdeniz": ["antalya", "adana", "mersin", "hatay", "tr-07", "tr-01", "tr-33"],
    "icanadolu": ["ankara", "konya", "eskisehir", "eskişehir", "tr-06", "tr-42", "tr-26"],
    "karadeniz": ["samsun", "trabzon", "ordu", "tr-55", "tr-61"],
    "dogu": ["erzurum", "van", "diyarbakir", "diyarbakır", "tr-25"],
    "guneydogu": ["gaziantep", "sanliurfa", "şanlıurfa", "tr-27"],
}


def region_search_terms(region: str) -> list[str]:
    key = region.strip().lower().replace(" ", "_").replace("-", "_")
    if key in REGION_ALIASES:
        return REGION_ALIASES[key]
    return [region.strip()]

from __future__ import annotations

import re
import unicodedata
from typing import Optional


def normalize_agent_text(text: str) -> str:
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

# Serbest metin q çıkarımında atlanacak kelimeler
QUERY_STOP_WORDS = frozenset(
    {
        "marka", "markalari", "markalar", "franchise", "bayilik", "bayilikleri",
        "icin", "için", "alti", "altı", "uygun", "firsat", "fırsat", "lari", "ler",
        "bin", "milyon", "tl", "kadar", "butceme", "butcem", "butce", "bana", "sana",
        "onerir", "önerir", "onerirsin", "önerirsin", "oner", "öner", "misin", "mısın",
        "iyi", "hangi", "en", "var", "mi", "mı", "ne", "nasil", "nasıl", "istiyorum",
        "kurmak", "is", "iş", "yapabilirim", "yapabilir", "ile", "ve", "olsun",
        "goster", "göster", "peki", "ya", "bir", "the", "hakkinda", "hakkında",
        "bilgi", "detay", "yardim", "yardım", "et", "selam", "merhaba", "tavsiye",
        "oneri", "öneri", "gore", "göre", "lutfen", "lütfen", "istiyorum", "arayan",
        "arayabilir", "olan", "olanlar", "olanlari", "neler", "nelerdir", "hangileri",
        "listele", "gosterir", "gösterir", "bak", "bakalim", "bakalım", "acaba",
        "cok", "çok", "az", "daha", "bana", "size", "siz", "benim", "ben", "su", "şu",
        "bu", "da", "de", "ta", "te", "ki", "mi", "mu", "mü", "midir", "mıdır",
    }
)

CITY_SUFFIX_RE = re.compile(r"(istanbul|ankara|izmir|bursa|antalya)(?:da|de|ta|te)?\b")


def strip_city_suffix(norm: str) -> Optional[str]:
    m = CITY_SUFFIX_RE.search(norm)
    return m.group(1) if m else None


def pick_best_free_token(tokens: list[str]) -> Optional[str]:
    candidates = [
        t
        for t in tokens
        if 3 <= len(t) <= 14
        and t not in QUERY_STOP_WORDS
        and not t.isdigit()
        and t not in ("gida", "gıda", "marmara", "istanbulda", "ankarada", "izmirde")
    ]
    return candidates[0] if candidates else None

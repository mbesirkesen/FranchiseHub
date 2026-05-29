from __future__ import annotations

import re


def sanitize_agent_query(query: str) -> str:
    """Kontrol karakterleri ve aşırı boşlukları temizle."""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", query)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

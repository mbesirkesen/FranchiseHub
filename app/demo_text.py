"""Seed/demo metinlerinden kullanıcıya görünen [DEMO] işaretlerini temizler."""
from __future__ import annotations

import re

_DEMO_PREFIX = re.compile(r"\[DEMO\]\s*")


def strip_demo_markers(text: str | None) -> str | None:
    if not text:
        return text
    cleaned = _DEMO_PREFIX.sub("", text).replace(" — [DEMO]", "")
    cleaned = cleaned.strip()
    return cleaned or None

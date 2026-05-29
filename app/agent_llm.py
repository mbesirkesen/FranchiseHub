from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Optional

from .agent_config import (
    AGENT_LLM_ENABLED,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
)

_log = logging.getLogger("franchisehub.agent.llm")


def maybe_enhance_answer(
    *,
    query: str,
    draft_answer: str,
    intent: str,
    brand_names: list[str],
    filters_human: str,
) -> tuple[str, str]:
    """
    Kurallar marka listesini üretir; LLM yalnızca Türkçe cevap metnini cilalar.
    API key yoksa veya hata olursa draft döner. source: rules | hybrid
    """
    if not AGENT_LLM_ENABLED or not OPENAI_API_KEY:
        return draft_answer, "rules"

    system = (
        "Sen FranchiseHub alıcı asistanısın. Yalnızca verilen taslak cevabı Türkçe, "
        "kısa ve samimi şekilde yeniden yaz. Yeni marka, fiyat veya ROI uydurma. "
        "Marka listesi değişmez; sadece metni iyileştir."
    )
    user_payload = {
        "user_query": query[:500],
        "intent": intent,
        "filters": filters_human,
        "brands_mentioned": brand_names[:6],
        "draft_answer": draft_answer,
    }
    try:
        body = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "temperature": 0.3,
            "max_tokens": 280,
        }
        req = urllib.request.Request(
            f"{OPENAI_BASE_URL}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        if text and len(text) <= 2000:
            return text, "hybrid"
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
        _log.warning("LLM enhance failed: %s", exc)
    return draft_answer, "rules"

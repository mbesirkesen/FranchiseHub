from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .agent_nlu_helpers import normalize_agent_text


@dataclass
class FoNluResult:
    intent: str
    tool_name: str
    arguments: dict


# NOT: classify_fo_query normalize edilmiş (accent'siz) metinle çalışır,
# bu yüzden desenler de accent'siz ve ek-toleranslı (kelime sınırı yok).
_GREETING = re.compile(r"^(merhaba|selam|hey|gunaydin|iyi gunler|iyi aksamlar|hello|hi)", re.I)
_THANKS = re.compile(r"(tesekkur|sagol|saol|eyvallah|teskler|tesekkler|tsk|saolun)", re.I)


def classify_fo_query(query: str) -> Optional[FoNluResult]:
    q = normalize_agent_text(query)
    if not q or len(q) < 2:
        return None

    if _GREETING.search(q):
        return FoNluResult("general", "fo_general_help", {"tone": "greeting"})
    if _THANKS.search(q):
        return FoNluResult("general", "fo_general_help", {"tone": "thanks"})

    if any(k in q for k in ("düşük stok", "dusuk stok", "stok az", "stok durum", "low stock")):
        scope = "all"
        if "şube" in q or "sube" in q:
            scope = "outlet"
        elif "merkez" in q:
            scope = "center"
        return FoNluResult("low_stock", "get_low_stock", {"scope": scope})

    if any(k in q for k in ("tedarik", "supply", "sipariş", "siparis")):
        status = "pending"
        if "onay" in q:
            status = "approved"
        elif "red" in q:
            status = "rejected"
        elif "kargo" in q or "sevk" in q:
            status = "shipped"
        incoming = "şube" in q or "sube" in q
        return FoNluResult(
            "supply_requests",
            "list_supply_requests",
            {"status": status, "incoming_only": incoming},
        )

    if any(k in q for k in ("başvuru", "basvuru", "application", "aday")):
        return FoNluResult("pending_applications", "list_pending_applications", {})

    if any(k in q for k in ("özet", "ozet", "dashboard", "panel", "durum", "rapor")):
        return FoNluResult("dashboard", "owner_dashboard_summary", {})

    if any(k in q for k in ("şube", "sube", "outlet", "lokasyon")):
        return FoNluResult("outlets", "list_my_outlets", {})

    if any(k in q for k in ("yardım", "yardim", "ne yapabilir", "neler sor")):
        return FoNluResult("general", "fo_general_help", {"tone": "help"})

    return None

from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .buyer_service import recommend_brands, score_brand_match
from .models import Brand, Buyer
from .region_filters import region_search_terms
from .schemas import (
    AssistantQueryRequest,
    AssistantQueryResponse,
    AssistantSuggestion,
    BrandRead,
)


def _detect_intent(query: str) -> str:
    q = query.lower()
    if any(w in q for w in ("karşılaştır", "compare", "fark")):
        return "compare"
    if any(w in q for w in ("bütçe", "budget", "maliyet", "yatırım")):
        return "budget"
    if any(w in q for w in ("sektör", "sector", "kafe", "restoran")):
        return "sector"
    if any(w in q for w in ("başvuru", "application", "süreç")):
        return "application_process"
    return "general"


def _extract_filters(query: str, buyer: Buyer) -> dict[str, object]:
    q = query.lower()
    filters: dict[str, object] = {
        "investment_budget": buyer.investment_budget,
        "preferred_sector": buyer.preferred_sector,
        "city": buyer.city,
    }
    for region_key in ("marmara", "ege", "akdeniz", "icanadolu", "karadeniz"):
        if region_key in q:
            filters["region"] = region_key
            filters["region_terms"] = region_search_terms(region_key)
            break
    if "fast" in q or "fast-food" in q or "hamburger" in q:
        filters["sector_hint"] = "fast-food"
    return filters


def answer_buyer_assistant(
    db: Session,
    buyer: Buyer,
    payload: AssistantQueryRequest,
) -> AssistantQueryResponse:
    intent = _detect_intent(payload.query)
    suggestions: list[AssistantSuggestion] = []
    related_brand_ids: list[int] = []
    filters_applied = _extract_filters(payload.query, buyer)

    recs = recommend_brands(
        db,
        investment_budget=buyer.investment_budget,
        preferred_sector=buyer.preferred_sector,
        experience_years=buyer.experience_years,
        city=buyer.city,
        limit=5,
    )
    related_brand_ids = [r.brand.id for r in recs]

    if payload.brand_id is not None:
        brand = db.scalar(
            select(Brand).where(
                Brand.id == payload.brand_id,
                Brand.is_approved.is_(True),
            )
        )
        if brand:
            score, reasons = score_brand_match(
                brand,
                investment_budget=buyer.investment_budget,
                preferred_sector=buyer.preferred_sector,
                experience_years=buyer.experience_years,
                city=buyer.city,
            )
            answer = (
                f"{brand.name} markası profilinizle %{score} uyumlu görünüyor. "
                + (" ".join(reasons) if reasons else "Detaylı karşılaştırma için marka sayfasını inceleyin.")
            )
            if brand.id not in related_brand_ids:
                related_brand_ids.insert(0, brand.id)
            return AssistantQueryResponse(
                answer=answer,
                intent=intent,
                suggestions=suggestions,
                related_brands=[BrandRead.model_validate(brand)],
                related_brand_ids=related_brand_ids,
                filters_applied=filters_applied,
                source="rules",
            )

    if intent == "budget":
        answer = (
            f"Yatırım bütçeniz {buyer.investment_budget:,.0f} TRY. "
            f"Bu aralıkta {len(recs)} onaylı marka önerisi var. "
            "Karşılaştırma için favorilerinize ekleyip POST /brands/compare kullanabilirsiniz."
        )
    elif intent == "sector":
        answer = (
            f"Tercih ettiğiniz sektör: {buyer.preferred_sector}. "
            f"Size uygun {len(recs)} marka listelendi; en yüksek skorlu markayı incelemenizi öneririm."
        )
    elif intent == "application_process":
        answer = (
            "Başvuru akışı: marka seçimi → POST /applications → franchise sahibi onayı → "
            "onay sonrası mesajlaşma açılır. Başvuru durumunuzu GET /applications/mine ile takip edebilirsiniz."
        )
    elif intent == "compare" and len(recs) >= 2:
        names = ", ".join(r.brand.name for r in recs[:3])
        answer = f"Karşılaştırma için önerilen markalar: {names}. POST /brands/compare ile yan yana analiz alın."
    else:
        clean = re.sub(r"\s+", " ", payload.query.strip())
        answer = (
            f"Sorunuz: «{clean[:120]}». "
            f"Profilinize göre {len(recs)} marka önerildi. "
            "Daha net yanıt için bütçe, sektör veya marka adı belirtebilirsiniz."
        )

    for rec in recs[:3]:
        suggestions.append(
            AssistantSuggestion(
                label=rec.brand.name,
                action="view_brand",
                brand_id=rec.brand.id,
                match_score=rec.match_score,
            )
        )

    return AssistantQueryResponse(
        answer=answer,
        intent=intent,
        suggestions=suggestions,
        related_brands=[r.brand for r in recs[:5]],
        related_brand_ids=related_brand_ids,
        filters_applied=filters_applied,
        source="rules",
    )

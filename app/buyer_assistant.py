from __future__ import annotations

import re
import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .agent_context import AgentBuyerContext, favorite_brands
from .agent_llm import maybe_enhance_answer
from .agent_nlu import (
    AgentSearchFilters,
    classify_intent,
    filters_applied_dict,
    filters_human_label,
    parse_agent_query,
)
from .brand_metrics import batch_estimated_roi_percent, build_brand_metrics
from .brand_service import build_compare_response, build_territory_list, list_approved_brands
from .buyer_service import score_brand_match
from .models import Application, Brand, Buyer
from .schemas import (
    AssistantBrandRead,
    AssistantQueryRequest,
    AssistantQueryResponse,
    AssistantSuggestion,
    BrandCompareResponse,
    BrandRead,
    BrandSort,
)


AGENT_RESULT_LIMIT = 4
AGENT_CANDIDATE_POOL = 40


def _rank_agent_brands(
    brands: list[Brand],
    *,
    buyer: Buyer,
    filters: AgentSearchFilters,
    roi_map: dict[int, float],
) -> list[tuple[Brand, int, list[str], float]]:
    scored: list[tuple[Brand, int, list[str], float]] = []
    for brand in brands:
        match_score, reasons = score_brand_match(
            brand,
            investment_budget=buyer.investment_budget,
            preferred_sector=buyer.preferred_sector,
            experience_years=buyer.experience_years,
            city=buyer.city,
        )
        if filters.max_cost is not None and float(brand.initial_cost) > filters.max_cost * 1.05:
            continue
        if filters.min_cost is not None and float(brand.initial_cost) < filters.min_cost:
            continue
        roi = roi_map.get(brand.id, 0.0)
        composite = match_score + min(roi, 30) * 0.5
        scored.append((brand, match_score, reasons, composite))
    scored.sort(key=lambda x: (-x[3], float(x[0].initial_cost)))
    return scored


def _to_assistant_brand(
    brand: Brand,
    *,
    match_score: int,
    match_reasons: list[str],
    estimated_roi_percent: float,
) -> AssistantBrandRead:
    base = BrandRead.model_validate(brand)
    return AssistantBrandRead(
        **base.model_dump(),
        estimated_roi_percent=estimated_roi_percent,
        match_score=match_score,
        match_reasons=match_reasons,
    )


def _default_suggestions(brands: list[AssistantBrandRead]) -> list[AssistantSuggestion]:
    suggestions: list[AssistantSuggestion] = []
    for ab in brands:
        suggestions.append(
            AssistantSuggestion(
                label=f"{ab.name} detayına git",
                action="open_brand",
                brand_id=ab.id,
                match_score=ab.match_score,
            )
        )
        suggestions.append(
            AssistantSuggestion(
                label=f"{ab.name} için başvur",
                action="start_application",
                brand_id=ab.id,
                match_score=ab.match_score,
            )
        )
        if ab.match_score and ab.match_score >= 70:
            suggestions.append(
                AssistantSuggestion(
                    label="Favorilere ekle",
                    action="add_favorite",
                    brand_id=ab.id,
                    match_score=ab.match_score,
                )
            )
    return suggestions[:8]


def _refine_suggestions() -> list[AssistantSuggestion]:
    return [
        AssistantSuggestion(label="Bütçe belirt (ör. 500 bin TL)", action="refine_search"),
        AssistantSuggestion(label="Sektör belirt (gıda, kahve)", action="refine_search"),
        AssistantSuggestion(label="Bölge belirt (Marmara, İstanbul)", action="refine_search"),
    ]


def _build_brand_search_answer(
    *,
    filters: AgentSearchFilters,
    buyer: Buyer,
    count: int,
) -> str:
    human = filters_human_label(filters, float(buyer.investment_budget))
    if count == 0:
        return (
            f"Bu kriterlerle eşleşen marka bulamadım ({human}). "
            "Farklı bir soru deneyin; örneğin sektör, bölge veya bütçe belirtebilirsiniz."
        )
    if filters.use_profile_budget:
        return (
            f"Profilinizdeki {buyer.investment_budget:,.0f} TL bütçeye göre {count} marka öneriyorum:"
        )
    return f"{human} için {count} fırsat buldum:"


def _search_brands_for_agent(
    db: Session,
    buyer: Buyer,
    filters: AgentSearchFilters,
    ctx: AgentBuyerContext,
) -> tuple[list[AssistantBrandRead], list[int]]:
    exclude = ctx.exclude_brand_ids
    if filters.exclude_applied:
        exclude = exclude | set(ctx.applied_brand_ids)

    items, _total = list_approved_brands(
        db,
        sector=filters.sector,
        min_cost=filters.min_cost,
        max_cost=filters.max_cost,
        location=filters.location,
        region=filters.region,
        q=filters.q,
        page=1,
        page_size=AGENT_CANDIDATE_POOL,
        sort=BrandSort.cost_asc,
    )
    items = [b for b in items if b.id not in exclude]
    roi_map = batch_estimated_roi_percent(db, items)
    ranked = _rank_agent_brands(
        items, buyer=buyer, filters=filters, roi_map=roi_map
    )[:AGENT_RESULT_LIMIT]

    assistant_brands: list[AssistantBrandRead] = []
    ids: list[int] = []
    for brand, match_score, reasons, _ in ranked:
        roi = roi_map.get(brand.id, 12.0)
        assistant_brands.append(
            _to_assistant_brand(
                brand,
                match_score=match_score,
                match_reasons=reasons,
                estimated_roi_percent=roi,
            )
        )
        ids.append(brand.id)
    return assistant_brands, ids


def _resolve_brands_by_names(db: Session, names: list[str]) -> list[Brand]:
    found: list[Brand] = []
    seen: set[int] = set()
    for name in names:
        pattern = f"%{name.strip()}%"
        row = db.scalar(
            select(Brand).where(
                Brand.is_approved.is_(True),
                Brand.name.ilike(pattern),
            )
        )
        if row and row.id not in seen:
            seen.add(row.id)
            found.append(row)
    return found


def _compare_answer(
    db: Session, buyer: Buyer, nlu_names: list[str]
) -> AssistantQueryResponse:
    brands = _resolve_brands_by_names(db, nlu_names)
    if len(brands) < 2:
        return AssistantQueryResponse(
            answer=(
                "Karşılaştırma için iki marka adı yazın. "
                "Örnek: «Komagene ile Starbucks karşılaştır»."
            ),
            intent="brand_compare",
            suggestions=_refine_suggestions(),
            source="rules",
        )
    pair = brands[:4]
    compare: BrandCompareResponse = build_compare_response(pair)
    cost_row = next((r for r in compare.comparison_table.rows if r.key == "initial_cost"), None)
    parts = [f"{c.name}" for c in compare.comparison_table.columns]
    answer = f"{' ve '.join(parts)} karşılaştırması: "
    if cost_row and cost_row.values:
        answer += "Yatırım maliyetleri — " + ", ".join(
            f"{compare.comparison_table.columns[i].name}: {cost_row.values[i] or '—'}"
            for i in range(min(len(cost_row.values), len(compare.comparison_table.columns)))
        )
        answer += "."
    assistant = []
    roi_map = batch_estimated_roi_percent(db, pair)
    for b in pair:
        score, reasons = score_brand_match(
            b,
            investment_budget=buyer.investment_budget,
            preferred_sector=buyer.preferred_sector,
            experience_years=buyer.experience_years,
            city=buyer.city,
        )
        assistant.append(
            _to_assistant_brand(
                b,
                match_score=score,
                match_reasons=reasons,
                estimated_roi_percent=roi_map.get(b.id, 12.0),
            )
        )
    return AssistantQueryResponse(
        answer=answer,
        intent="brand_compare",
        related_brands=assistant,
        related_brand_ids=[b.id for b in pair],
        compare=compare,
        suggestions=_default_suggestions(assistant),
        filters_applied={"brand_names": nlu_names},
        source="rules",
    )


def _favorites_similar_answer(
    db: Session,
    buyer: Buyer,
    ctx: AgentBuyerContext,
) -> AssistantQueryResponse:
    favs = favorite_brands(db, buyer.id)
    if not favs:
        return AssistantQueryResponse(
            answer="Henüz favori markanız yok. Keşfet sayfasından favorilere ekleyebilirsiniz.",
            intent="favorites_similar",
            suggestions=[
                AssistantSuggestion(label="Marka keşfet", action="refine_search"),
            ],
            source="rules",
        )
    sectors = {f.sector for f in favs if f.sector}
    filters = AgentSearchFilters()
    if len(sectors) == 1:
        filters.sector = next(iter(sectors))
    filters.similar_to_favorites = True
    ctx.exclude_brand_ids |= {f.id for f in favs}
    brands, ids = _search_brands_for_agent(db, buyer, filters, ctx)
    names = ", ".join(f.name for f in favs[:3])
    answer = f"Favorileriniz ({names}) ile benzer {len(brands)} marka:"
    return AssistantQueryResponse(
        answer=answer,
        intent="favorites_similar",
        related_brands=brands,
        related_brand_ids=ids,
        suggestions=_default_suggestions(brands),
        filters_applied=filters_applied_dict(filters),
        source="rules",
    )


def _territory_answer(
    db: Session,
    buyer: Buyer,
    brand_id: int,
    query: str,
) -> AssistantQueryResponse:
    brand = db.scalar(
        select(Brand).where(Brand.id == brand_id, Brand.is_approved.is_(True))
    )
    if not brand:
        return AssistantQueryResponse(
            answer="Marka bulunamadı.",
            intent="territory_check",
            source="rules",
        )
    territories = build_territory_list(db, brand_id)
    available = [t for t in territories.items if t.status == "available"]
    norm = query.lower()
    city_filter = None
    for key in ("istanbul", "ankara", "izmir", "bursa", "antalya"):
        if key in norm:
            city_filter = key
            break
    if city_filter:
        available = [
            t
            for t in available
            if city_filter in (t.name or "").lower()
            or city_filter in (t.region_code or "").lower()
        ]
    if available:
        names = ", ".join(t.name for t in available[:5])
        answer = f"{brand.name} için {len(available)} müsait bölge: {names}."
    else:
        answer = f"{brand.name} için şu an müsait bölge görünmüyor; franchise sahibiyle iletişime geçebilirsiniz."
    return AssistantQueryResponse(
        answer=answer,
        intent="territory_check",
        related_brand_ids=[brand.id],
        filters_applied={"brand_id": brand_id, "available_count": len(available)},
        source="rules",
    )


def _application_status_answer(db: Session, buyer: Buyer) -> AssistantQueryResponse:
    apps = db.scalars(
        select(Application)
        .where(Application.buyer_id == buyer.id)
        .order_by(Application.created_at.desc())
    ).all()
    if not apps:
        return AssistantQueryResponse(
            answer="Henüz bir başvurunuz yok. Keşfet sayfasından marka seçip başvuru oluşturabilirsiniz.",
            intent="application_status",
            suggestions=[AssistantSuggestion(label="Marka keşfet", action="refine_search")],
            source="rules",
        )
    brand_ids = [a.brand_id for a in apps[:5]]
    brands = db.scalars(
        select(Brand).where(Brand.id.in_(brand_ids))
    ).all()
    brand_map = {b.id: b.name for b in brands}
    lines = []
    for app in apps[:5]:
        status_tr = {
            "pending": "beklemede",
            "approved": "onaylandı",
            "rejected": "reddedildi",
        }.get(
            app.status.value if hasattr(app.status, "value") else str(app.status),
            str(app.status),
        )
        name = brand_map.get(app.brand_id, f"Marka #{app.brand_id}")
        lines.append(f"{name}: {status_tr}")
    return AssistantQueryResponse(
        answer="Başvuru durumlarınız — " + "; ".join(lines) + ".",
        intent="application_status",
        related_brand_ids=brand_ids,
        source="rules",
    )


def _brand_detail_answer(
    db: Session,
    buyer: Buyer,
    brand_id: int,
) -> AssistantQueryResponse:
    brand = db.scalar(
        select(Brand).where(Brand.id == brand_id, Brand.is_approved.is_(True))
    )
    if not brand:
        return AssistantQueryResponse(
            answer="Marka bulunamadı veya henüz onaylanmamış.",
            intent="brand_detail",
            source="rules",
        )
    metrics = build_brand_metrics(db, brand_id)
    score, reasons = score_brand_match(
        brand,
        investment_budget=buyer.investment_budget,
        preferred_sector=buyer.preferred_sector,
        experience_years=buyer.experience_years,
        city=buyer.city,
    )
    ab = _to_assistant_brand(
        brand,
        match_score=score,
        match_reasons=reasons,
        estimated_roi_percent=metrics.estimated_roi_percent,
    )
    growth_hint = ""
    if metrics.growth_series:
        last = metrics.growth_series[-1].value
        growth_hint = f" Son ay büyüme göstergesi: {last:.1f}."
    answer = (
        f"{brand.name}: tahmini ROI %{metrics.estimated_roi_percent:.1f}, "
        f"{metrics.outlet_count} şube, {metrics.territories_available} müsait bölge."
        + growth_hint
    )
    return AssistantQueryResponse(
        answer=answer,
        intent="brand_detail",
        related_brands=[ab],
        related_brand_ids=[brand.id],
        filters_applied={"brand_id": brand_id},
        suggestions=_default_suggestions([ab]),
        source="rules",
    )


def _maybe_llm_polish(
    response: AssistantQueryResponse,
    *,
    query: str,
    buyer: Buyer,
    filters: Optional[AgentSearchFilters] = None,
) -> AssistantQueryResponse:
    if response.intent not in ("brand_search", "favorites_similar", "brand_detail", "no_match"):
        return response
    human = filters_human_label(
        filters or AgentSearchFilters(),
        float(buyer.investment_budget),
    )
    names = [b.name for b in response.related_brands]
    enhanced, source = maybe_enhance_answer(
        query=query,
        draft_answer=response.answer,
        intent=response.intent,
        brand_names=names,
        filters_human=human,
    )
    response.answer = enhanced
    response.source = source
    return response


def answer_buyer_assistant(
    db: Session,
    buyer: Buyer,
    payload: AssistantQueryRequest,
    ctx: Optional[AgentBuyerContext] = None,
) -> AssistantQueryResponse:
    started = time.perf_counter()
    context = ctx or AgentBuyerContext()
    brand_id = payload.brand_id or payload.brand_context_id

    if brand_id is not None:
        intent = classify_intent(payload.query, brand_id)
        if intent == "territory_check":
            resp = _territory_answer(db, buyer, brand_id, payload.query)
            resp.latency_ms = int((time.perf_counter() - started) * 1000)
            return resp
        if intent == "brand_detail" or any(
            w in payload.query.lower()
            for w in ("roi", "getiri", "şube", "sube", "metrik", "trend")
        ):
            resp = _brand_detail_answer(db, buyer, brand_id)
            resp = _maybe_llm_polish(resp, query=payload.query, buyer=buyer)
            resp.latency_ms = int((time.perf_counter() - started) * 1000)
            return resp

    nlu = parse_agent_query(payload.query, buyer)
    intent = nlu.intent

    if intent == "application_status":
        resp = _application_status_answer(db, buyer)
        resp.latency_ms = int((time.perf_counter() - started) * 1000)
        return resp

    if intent == "brand_compare":
        resp = _compare_answer(db, buyer, nlu.compare_brand_names)
        resp.latency_ms = int((time.perf_counter() - started) * 1000)
        return resp

    if intent == "favorites_similar":
        resp = _favorites_similar_answer(db, buyer, context)
        resp = _maybe_llm_polish(resp, query=payload.query, buyer=buyer, filters=nlu.filters)
        resp.latency_ms = int((time.perf_counter() - started) * 1000)
        return resp

    if intent == "general":
        return AssistantQueryResponse(
            answer=(
                "FranchiseHub'da onaylı markaları keşfedebilir, bütçe ve sektörünüze göre "
                "filtreleyebilir ve başvuru oluşturabilirsiniz. "
                "Örnek: «500 bin TL altı gıda markaları» veya «İstanbul'da kahve franchise»."
            ),
            intent="general",
            suggestions=_refine_suggestions(),
            source="rules",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    if intent == "no_match":
        return AssistantQueryResponse(
            answer=(
                "Sorunuzu tam anlayamadım. Bütçe (ör. 500 bin TL), sektör (gıda, kahve), "
                "bölge (Marmara) veya şehir (İstanbul) belirterek tekrar deneyin."
            ),
            intent="no_match",
            suggestions=_refine_suggestions(),
            source="rules",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    if nlu.filters.exclude_applied:
        context.exclude_brand_ids |= set(context.applied_brand_ids)

    brands, brand_ids = _search_brands_for_agent(db, buyer, nlu.filters, context)
    answer = _build_brand_search_answer(
        filters=nlu.filters, buyer=buyer, count=len(brands)
    )
    suggestions = _default_suggestions(brands)
    if not brands:
        suggestions = _refine_suggestions()

    resp = AssistantQueryResponse(
        answer=answer,
        intent="brand_search",
        suggestions=suggestions,
        related_brands=brands,
        related_brand_ids=brand_ids,
        filters_applied=filters_applied_dict(nlu.filters),
        source="rules",
    )
    resp = _maybe_llm_polish(resp, query=payload.query, buyer=buyer, filters=nlu.filters)
    resp.latency_ms = int((time.perf_counter() - started) * 1000)
    return resp

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
    _detect_ordinal_index,
    _detect_pick_mode,
    _normalize,
    build_profile_recommendation_filters,
    classify_intent,
    extract_brand_name_tokens,
    filters_applied_dict,
    filters_human_label,
    parse_agent_query,
)
from .brand_metrics import (
    batch_brand_compare_snapshots,
    batch_estimated_roi_percent,
    build_brand_metrics,
    build_compare_insights_text,
)
from .brand_service import build_compare_response, build_territory_list, list_approved_brands
from .brand_vector_search import semantic_brand_search
from .buyer_service import score_brand_match
from .models import Application, ApplicationStatus, Brand, Buyer
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

COMPARE_DISCLAIMER = (
    " Bu karşılaştırma yalnızca bilgilendirme amaçlıdır; yatırım tavsiyesi değildir. "
    "Gelecekteki getiri veya iş sonuçları garanti edilmez — karar vermeden önce kendi "
    "araştırmanızı yapmanızı öneririz."
)


def _with_compare_disclaimer(answer: str) -> str:
    if COMPARE_DISCLAIMER.strip() in answer:
        return answer
    return answer.rstrip() + COMPARE_DISCLAIMER


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
        scored.append((brand, match_score, reasons, composite, roi))
    if filters.sort == "roi_desc":
        scored.sort(key=lambda x: (-x[4], -x[1], float(x[0].initial_cost)))
    elif filters.sort == "cost_desc":
        scored.sort(key=lambda x: (-float(x[0].initial_cost), -x[1]))
    else:
        scored.sort(key=lambda x: (-x[3], float(x[0].initial_cost)))
    return [(b, ms, rs, comp) for b, ms, rs, comp, _ in scored]


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


def _compare_suggestions(
    db: Session,
    ctx: Optional[AgentBuyerContext] = None,
    *,
    brands: Optional[list[Brand]] = None,
) -> list[AssistantSuggestion]:
    """Karşılaştırma bağlamında marka adı örnekleri — bütçe/sektör chip'leri değil."""
    suggestions: list[AssistantSuggestion] = []
    pair: list[Brand] = list(brands or [])

    if len(pair) < 2 and ctx:
        snap = ctx.session_snapshot or ctx.last_search_state or {}
        compare_ids = [int(x) for x in snap.get("compare_brand_ids") or []]
        if len(compare_ids) >= 2:
            pair = _brands_by_ids(db, compare_ids[:4])
        elif snap.get("related_brand_ids"):
            list_ids = [int(x) for x in snap["related_brand_ids"][:4]]
            pair = _brands_by_ids(db, list_ids)

    if len(pair) >= 2:
        for i in range(min(len(pair) - 1, 2)):
            a, b = pair[i], pair[i + 1]
            suggestions.append(
                AssistantSuggestion(
                    label=f"{a.name} ile {b.name} karşılaştır",
                    action="refine_search",
                )
            )
        if len(pair) >= 3:
            suggestions.append(
                AssistantSuggestion(
                    label=f"{pair[0].name} ile {pair[2].name} karşılaştır",
                    action="refine_search",
                )
            )

    if not suggestions:
        fallback = list(
            db.scalars(
                select(Brand)
                .where(Brand.is_approved.is_(True))
                .order_by(Brand.id.asc())
                .limit(4)
            ).all()
        )
        if len(fallback) >= 2:
            suggestions.append(
                AssistantSuggestion(
                    label=f"{fallback[0].name} ile {fallback[1].name} karşılaştır",
                    action="refine_search",
                )
            )
            if len(fallback) >= 3:
                suggestions.append(
                    AssistantSuggestion(
                        label=f"{fallback[0].name} ile {fallback[2].name} karşılaştır",
                        action="refine_search",
                    )
                )

    if not suggestions:
        suggestions = [
            AssistantSuggestion(
                label="Pizza Pro ile Komagene Hub karşılaştır",
                action="refine_search",
            ),
            AssistantSuggestion(
                label="Brew Max ile Clean TR karşılaştır",
                action="refine_search",
            ),
        ]

    return suggestions[:4]


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
            "Bütçeyi artırabilir, farklı sektör deneyebilir veya «bana uygun marka öner» yazabilirsiniz."
        )
    if filters.use_profile_budget:
        return (
            f"Profilinizdeki {buyer.investment_budget:,.0f} TL bütçeye göre {count} marka öneriyorum:"
        )
    if filters.max_cost is not None:
        return f"{filters.max_cost:,.0f} TL bütçenize uygun {count} fırsat buldum:"
    return f"{human} için {count} fırsat buldum:"


def _build_relaxed_search_note(
    original: AgentSearchFilters,
    used: AgentSearchFilters,
    *,
    brands: list[AssistantBrandRead],
) -> str:
    if not brands:
        return ""
    budget_ceiling = original.max_cost
    budget_ok = budget_ceiling is None or all(
        float(b.initial_cost) <= budget_ceiling * 1.05 for b in brands
    )
    if original.sector and not used.sector:
        if budget_ok and budget_ceiling:
            return (
                f"«{original.sector}» sektöründe seçenek sınırlı; "
                f"{budget_ceiling:,.0f} TL bütçenize uygun diğer markalar:"
            )
        return f"«{original.sector}» sektöründe uygun marka bulamadım. Bunun yerine "
    if original.q and not used.q and not used.sector:
        if budget_ok and budget_ceiling:
            return (
                f"«{original.q}» için tam eşleşme yok; "
                f"{budget_ceiling:,.0f} TL bütçenize uygun yakın markalar:"
            )
        return f"«{original.q}» için tam eşleşme bulamadım. Yakın olarak "
    return ""


def _search_brands_for_agent(
    db: Session,
    buyer: Buyer,
    filters: AgentSearchFilters,
    ctx: AgentBuyerContext,
) -> tuple[list[AssistantBrandRead], list[int]]:
    exclude = ctx.exclude_brand_ids
    if filters.exclude_applied:
        exclude = exclude | set(ctx.applied_brand_ids)

    sort = BrandSort.cost_desc if filters.sort == "cost_desc" else BrandSort.cost_asc
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
        sort=sort,
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


def _search_brands_by_ids(
    db: Session,
    buyer: Buyer,
    brand_ids: list[int],
    ctx: AgentBuyerContext,
    filters: AgentSearchFilters,
) -> tuple[list[AssistantBrandRead], list[int]]:
    if not brand_ids:
        return [], []
    rows = list(
        db.scalars(
            select(Brand).where(
                Brand.id.in_(brand_ids),
                Brand.is_approved.is_(True),
            )
        ).all()
    )
    exclude = ctx.exclude_brand_ids
    if filters.exclude_applied:
        exclude = exclude | set(ctx.applied_brand_ids)
    rows = [b for b in rows if b.id not in exclude]
    order = {bid: i for i, bid in enumerate(brand_ids)}
    rows.sort(key=lambda b: order.get(b.id, 999))
    roi_map = batch_estimated_roi_percent(db, rows)
    ranked = _rank_agent_brands(rows, buyer=buyer, filters=filters, roi_map=roi_map)[
        :AGENT_RESULT_LIMIT
    ]
    assistant_brands: list[AssistantBrandRead] = []
    ids: list[int] = []
    for brand, match_score, reasons, _ in ranked:
        assistant_brands.append(
            _to_assistant_brand(
                brand,
                match_score=match_score,
                match_reasons=reasons,
                estimated_roi_percent=roi_map.get(brand.id, 12.0),
            )
        )
        ids.append(brand.id)
    return assistant_brands, ids


def _search_with_relaxed_filters(
    db: Session,
    buyer: Buyer,
    filters: AgentSearchFilters,
    ctx: AgentBuyerContext,
) -> tuple[list[AssistantBrandRead], list[int], AgentSearchFilters]:
    brands, ids = _search_brands_for_agent(db, buyer, filters, ctx)
    if brands:
        return brands, ids, filters

    relaxed = AgentSearchFilters(**{k: v for k, v in filters.__dict__.items()})

    # Bütçe tavanı korunur; sektör/şehir/bölge daraltıcıysa önce onları gevşet.
    if relaxed.sector or relaxed.location or relaxed.region:
        scope_relaxed = AgentSearchFilters(**{k: v for k, v in relaxed.__dict__.items()})
        scope_relaxed.sector = None
        scope_relaxed.use_profile_sector = False
        scope_relaxed.location = None
        scope_relaxed.region = None
        scope_relaxed.use_profile_city = False
        brands, ids = _search_brands_for_agent(db, buyer, scope_relaxed, ctx)
        if brands:
            return brands, ids, scope_relaxed

    if relaxed.q:
        relaxed.q = None
        brands, ids = _search_brands_for_agent(db, buyer, relaxed, ctx)
        if brands:
            return brands, ids, relaxed

    if relaxed.min_cost is not None:
        relaxed.min_cost = None
        brands, ids = _search_brands_for_agent(db, buyer, relaxed, ctx)
        if brands:
            return brands, ids, relaxed

    # Düşük bütçe tavanında (ör. 500 bin) hafif gevşet; yüksek bütçede anlamsız.
    if relaxed.max_cost is not None and relaxed.max_cost < 2_000_000:
        relaxed.max_cost = relaxed.max_cost * 1.2
        brands, ids = _search_brands_for_agent(db, buyer, relaxed, ctx)
        if brands:
            return brands, ids, relaxed

    if relaxed.sector:
        relaxed.sector = None
        relaxed.use_profile_sector = False
        brands, ids = _search_brands_for_agent(db, buyer, relaxed, ctx)
        if brands:
            return brands, ids, relaxed

    return [], [], filters


def _try_resolve_single_brand(
    db: Session, norm: str, vocabulary=None
) -> Optional[Brand]:
    if vocabulary:
        ids = vocabulary.match_brand_ids(norm, limit=1)
        if len(ids) == 1:
            return db.get(Brand, ids[0])
    for name in extract_brand_name_tokens(norm):
        resolved = _resolve_brands_by_names(db, [name])
        if len(resolved) == 1:
            return resolved[0]
    tokens = [t for t in re.split(r"\s+", norm) if len(t) >= 4]
    for token in tokens:
        resolved = _resolve_brands_by_names(db, [token.capitalize()])
        if len(resolved) == 1:
            return resolved[0]
    return None


def _pick_from_previous_brands(
    db: Session,
    buyer: Buyer,
    *,
    brand_ids: list[int],
    pick_mode: str,
    pick_index: Optional[int] = None,
) -> AssistantQueryResponse:
    rows = list(
        db.scalars(
            select(Brand).where(Brand.id.in_(brand_ids), Brand.is_approved.is_(True))
        ).all()
    )
    if not rows:
        return AssistantQueryResponse(
            answer="Önceki listede marka bulamadım. Yeni bir arama yapabilirsiniz.",
            intent="brand_pick",
            suggestions=_refine_suggestions(),
            source="rules",
        )

    roi_map = batch_estimated_roi_percent(db, rows)
    scored: list[tuple[Brand, int, list[str], float]] = []
    for brand in rows:
        match_score, reasons = score_brand_match(
            brand,
            investment_budget=buyer.investment_budget,
            preferred_sector=buyer.preferred_sector,
            experience_years=buyer.experience_years,
            city=buyer.city,
        )
        roi = roi_map.get(brand.id, 12.0)
        scored.append((brand, match_score, reasons, float(brand.initial_cost)))

    if pick_mode == "cheapest":
        scored.sort(key=lambda x: x[3])
        label = "En ucuz"
    elif pick_mode == "expensive":
        scored.sort(key=lambda x: -x[3])
        label = "En yüksek yatırım gerektiren"
    elif pick_mode == "best_roi":
        scored.sort(key=lambda x: (-roi_map.get(x[0].id, 0.0), -x[1]))
        label = "En yüksek ROI'li"
    elif pick_mode == "ordinal" and pick_index is not None:
        scored.sort(key=lambda x: x[3])
        label = "Seçtiğiniz"
    else:
        scored.sort(key=lambda x: (-x[1], x[3]))
        label = "Profilinize en uygun"

    idx = 0
    if pick_mode == "ordinal" and pick_index is not None:
        idx = pick_index if pick_index >= 0 else len(scored) - 1
        idx = max(0, min(idx, len(scored) - 1))

    chosen, match_score, reasons, cost = scored[idx]
    assistant = _to_assistant_brand(
        chosen,
        match_score=match_score,
        match_reasons=reasons,
        estimated_roi_percent=roi_map.get(chosen.id, 12.0),
    )
    others = [
        f"{b.name} ({float(b.initial_cost):,.0f} TL)"
        for b, _, _, _ in scored[1:4]
    ]
    answer = (
        f"{label} seçenek: {chosen.name} — yatırım {float(chosen.initial_cost):,.0f} TL, "
        f"tahmini ROI %{roi_map.get(chosen.id, 12.0):.1f}."
    )
    if others:
        answer += " Diğerleri: " + ", ".join(others) + "."

    return AssistantQueryResponse(
        answer=answer,
        intent="brand_pick",
        related_brands=[assistant],
        related_brand_ids=[chosen.id],
        filters_applied={"pick_mode": pick_mode, "from_brand_ids": brand_ids},
        suggestions=_default_suggestions([assistant]),
        source="rules",
    )


def _resolve_brands_by_names(db: Session, names: list[str]) -> list[Brand]:
    """Marka adlarını Türkçe-duyarsız ve ek-toleranslı eşleştirir.
    'doner hub' -> 'Döner Hub', 'burger pointi' -> 'Burger Point' gibi."""
    approved = list(
        db.scalars(select(Brand).where(Brand.is_approved.is_(True))).all()
    )
    norm_index = [(b, _normalize(b.name)) for b in approved]

    found: list[Brand] = []
    seen: set[int] = set()
    for name in names:
        nq = _normalize(name)
        if not nq:
            continue
        q_tokens = [t for t in nq.split() if len(t) >= 3]
        best: Optional[Brand] = None
        best_score = 0
        for brand, nb in norm_index:
            if not nb:
                continue
            if nb in nq or (len(nq) >= 4 and nq in nb):
                score = 100 + len(nb)
            else:
                score = 0
                for qt in q_tokens:
                    for bt in nb.split():
                        if qt == bt:
                            score += 10
                        elif len(bt) >= 4 and (qt.startswith(bt) or bt.startswith(qt)):
                            score += 6
            if score > best_score:
                best_score = score
                best = brand
        # En az bir anlamlı token eşleşmesi (>=6) gerek; rastgele eşleşmeyi engelle
        if best is not None and best_score >= 6 and best.id not in seen:
            seen.add(best.id)
            found.append(best)
    return found


def _approved_franchise_brands(db: Session, buyer: Buyer) -> list[Brand]:
    brand_ids = [
        int(x)
        for x in db.scalars(
            select(Application.brand_id).where(
                Application.buyer_id == buyer.id,
                Application.status == ApplicationStatus.approved,
            )
        ).all()
    ]
    if not brand_ids:
        return []
    return list(
        db.scalars(
            select(Brand).where(
                Brand.id.in_(brand_ids),
                Brand.is_approved.is_(True),
            )
        ).all()
    )


def _brands_by_ids(db: Session, brand_ids: list[int]) -> list[Brand]:
    if not brand_ids:
        return []
    rows = db.scalars(
        select(Brand).where(
            Brand.id.in_(brand_ids),
            Brand.is_approved.is_(True),
        )
    ).all()
    by_id = {b.id: b for b in rows}
    return [by_id[i] for i in brand_ids if i in by_id]


def _resolve_anchor_brand(
    db: Session,
    *,
    anchor_brand_id: Optional[int],
    ctx: AgentBuyerContext,
    nlu_names: list[str],
) -> Optional[Brand]:
    if anchor_brand_id is not None:
        anchor = db.scalar(
            select(Brand).where(
                Brand.id == anchor_brand_id,
                Brand.is_approved.is_(True),
            )
        )
        if anchor:
            return anchor
    if ctx.last_search_state:
        prev_ids = ctx.last_search_state.get("related_brand_ids") or []
        if prev_ids:
            brands = _brands_by_ids(db, [int(prev_ids[0])])
            if brands:
                return brands[0]
    if len(nlu_names) == 1:
        resolved = _resolve_brands_by_names(db, nlu_names)
        if resolved:
            return resolved[0]
    return None


def _compose_compare_answer(
    db: Session,
    brands: list[Brand],
    *,
    header: str,
) -> tuple[str, BrandCompareResponse, dict[int, float]]:
    pair = brands[:4]
    snapshots = batch_brand_compare_snapshots(db, pair)
    roi_map = batch_estimated_roi_percent(db, pair)
    insights = build_compare_insights_text(pair, snapshots, roi_map)
    compare = build_compare_response(
        pair, snapshots=snapshots, roi_map=roi_map, insights=insights
    )
    cost_row = next(
        (r for r in compare.comparison_table.rows if r.key == "initial_cost"), None
    )
    answer = header.rstrip()
    if not answer.endswith(":") and not answer.endswith("."):
        answer += ":"
    if cost_row and cost_row.values:
        answer += " Yatırım maliyetleri — " + ", ".join(
            f"{compare.comparison_table.columns[i].name}: {cost_row.values[i] or '—'}"
            for i in range(min(len(cost_row.values), len(compare.comparison_table.columns)))
        ) + "."
    if insights:
        answer += "\n\n" + insights
    return answer, compare, roi_map


def _build_compare_response(
    db: Session,
    buyer: Buyer,
    brands: list[Brand],
    *,
    answer: str,
    filters_applied: Optional[dict] = None,
) -> AssistantQueryResponse:
    pair = brands[:4]
    snapshots = batch_brand_compare_snapshots(db, pair)
    roi_map = batch_estimated_roi_percent(db, pair)
    insights = build_compare_insights_text(pair, snapshots, roi_map)
    compare = build_compare_response(
        pair, snapshots=snapshots, roi_map=roi_map, insights=insights
    )
    full_answer = answer.rstrip()
    if insights and insights not in full_answer:
        full_answer += "\n\n" + insights
    assistant = []
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
        answer=_with_compare_disclaimer(full_answer),
        intent="brand_compare",
        related_brands=assistant,
        related_brand_ids=[b.id for b in pair],
        compare=compare,
        suggestions=_default_suggestions(assistant),
        filters_applied=filters_applied or {"brand_ids": [b.id for b in pair]},
        source="rules",
    )


def _compare_with_owned_franchises(
    db: Session,
    buyer: Buyer,
    *,
    anchor_brand_id: Optional[int],
    nlu_names: list[str],
    ctx: AgentBuyerContext,
) -> AssistantQueryResponse:
    owned = _approved_franchise_brands(db, buyer)
    if not owned:
        return AssistantQueryResponse(
            answer=(
                "Onaylı bayiliğiniz yok; mevcut bayiliklerinizle karşılaştırma yapılamaz. "
                "Önce bir markaya onaylı başvurunuz olmalı — veya iki marka adı yazarak karşılaştırın."
            ),
            intent="brand_compare",
            suggestions=_compare_suggestions(db, ctx),
            source="rules",
        )

    anchor = _resolve_anchor_brand(
        db,
        anchor_brand_id=anchor_brand_id,
        ctx=ctx,
        nlu_names=nlu_names,
    )
    brands: list[Brand] = []
    if anchor:
        brands.append(anchor)
        for brand in owned:
            if brand.id != anchor.id:
                brands.append(brand)
    else:
        brands = owned[:4]

    if len(brands) < 2:
        only = brands[0].name if brands else "Bayiliğiniz"
        return AssistantQueryResponse(
            answer=(
                f"Şu an yalnızca {only} için onaylı bayiliğiniz var. "
                "Karşılaştırma için önce başka bir marka arayın, sonra «bende olan bayiliklerimle karşılaştır» deyin."
            ),
            intent="brand_compare",
            suggestions=_compare_suggestions(db, ctx),
            source="rules",
        )

    if anchor:
        owned_names = ", ".join(b.name for b in owned[:3])
        answer = (
            f"{anchor.name} ile onaylı bayilikleriniz ({owned_names}) karşılaştırması:"
        )
    else:
        answer = "Onaylı bayiliklerinizin karşılaştırması:"

    answer, _, _ = _compose_compare_answer(db, brands[:4], header=answer)

    return _build_compare_response(
        db,
        buyer,
        brands[:4],
        answer=answer,
        filters_applied={"compare_with_owned": True, "anchor_brand_id": anchor.id if anchor else None},
    )


def _compare_with_previous_list(
    db: Session,
    buyer: Buyer,
    ctx: AgentBuyerContext,
) -> AssistantQueryResponse:
    snap = ctx.session_snapshot or ctx.last_search_state or {}
    compare_ids = [int(x) for x in snap.get("compare_brand_ids") or []]
    if len(compare_ids) >= 2:
        brands = _brands_by_ids(db, compare_ids[:4])
        if len(brands) >= 2:
            names = " ve ".join(b.name for b in brands[:2])
            suffix = " (tekrar)" if len(brands) == 2 else ""
            answer, _, _ = _compose_compare_answer(
                db, brands, header=f"{names} karşılaştırması{suffix}"
            )
            return _build_compare_response(
                db,
                buyer,
                brands,
                answer=answer,
                filters_applied={"repeat_compare": True, "brand_ids": compare_ids[:4]},
            )

    prev_ids = [int(x) for x in snap.get("related_brand_ids") or []]
    brands = _brands_by_ids(db, prev_ids[:4])
    if len(brands) < 2:
        return AssistantQueryResponse(
            answer=(
                "Karşılaştırma için iki marka adı yazın. "
                "Örnek: «Pizza Pro ile Komagene Hub karşılaştır»."
            ),
            intent="brand_compare",
            suggestions=_compare_suggestions(db, ctx),
            source="rules",
        )
    names = ", ".join(b.name for b in brands[:4])
    answer, _, _ = _compose_compare_answer(
        db, brands, header=f"Son aramanızdaki markalar ({names}) karşılaştırması"
    )
    return _build_compare_response(
        db,
        buyer,
        brands,
        answer=answer,
        filters_applied={"from_previous_search": True, "brand_ids": prev_ids[:4]},
    )


def _compare_answer(
    db: Session,
    buyer: Buyer,
    nlu_names: list[str],
    *,
    fallback_ids: Optional[list[int]] = None,
    ctx: Optional[AgentBuyerContext] = None,
) -> AssistantQueryResponse:
    brands = _resolve_brands_by_names(db, nlu_names)
    # İsimlerden 2 marka çözülemezse DB sözlüğü id'leriyle tamamla
    if len(brands) < 2 and fallback_ids:
        seen = {b.id for b in brands}
        for bid in fallback_ids:
            if bid in seen:
                continue
            extra = db.scalar(
                select(Brand).where(Brand.id == bid, Brand.is_approved.is_(True))
            )
            if extra is not None:
                brands.append(extra)
                seen.add(bid)
            if len(brands) >= 4:
                break
    if len(brands) < 2:
        return AssistantQueryResponse(
            answer=(
                "Karşılaştırma için iki marka adı yazın. "
                "Örnek: «Pizza Pro ile Komagene Hub karşılaştır»."
            ),
            intent="brand_compare",
            suggestions=_compare_suggestions(db, ctx),
            source="rules",
        )
    pair = brands[:4]
    parts = [b.name for b in pair]
    answer, _, _ = _compose_compare_answer(
        db, pair, header=f"{' ve '.join(parts)} karşılaştırması"
    )
    return _build_compare_response(
        db,
        buyer,
        pair,
        answer=answer,
        filters_applied={"brand_names": nlu_names},
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
    if response.intent not in (
        "brand_search",
        "favorites_similar",
        "brand_detail",
        "brand_pick",
        "no_match",
        "general",
    ):
        return response
    human = filters_human_label(
        filters or AgentSearchFilters(),
        float(buyer.investment_budget),
    )
    names = [b.name for b in response.related_brands]
    original_source = response.source
    enhanced, source = maybe_enhance_answer(
        query=query,
        draft_answer=response.answer,
        intent=response.intent,
        brand_names=names,
        filters_human=human,
    )
    response.answer = enhanced
    # Veri kaynağı sinyalini (semantic/llm_tools) koru; LLM yalnızca metni cilaladı.
    if original_source in ("semantic", "llm_tools"):
        response.source = original_source
    else:
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

    if brand_id is None:
        from .agent_router import try_llm_tool_route

        routed = try_llm_tool_route(db, buyer, payload, context)
        if routed is not None:
            routed.latency_ms = int((time.perf_counter() - started) * 1000)
            return routed

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

    nlu = parse_agent_query(
        payload.query,
        buyer,
        previous_search=context.last_search_state,
        vocabulary=context.vocabulary,
    )
    intent = nlu.intent

    if intent == "application_status":
        resp = _application_status_answer(db, buyer)
        resp.latency_ms = int((time.perf_counter() - started) * 1000)
        return resp

    if intent == "brand_compare":
        if nlu.compare_with_owned:
            resp = _compare_with_owned_franchises(
                db,
                buyer,
                anchor_brand_id=brand_id,
                nlu_names=nlu.compare_brand_names,
                ctx=context,
            )
        elif nlu.compare_with_previous and (context.last_search_state or context.session_snapshot):
            resp = _compare_with_previous_list(db, buyer, context)
        else:
            resp = _compare_answer(
                db,
                buyer,
                nlu.compare_brand_names,
                fallback_ids=nlu.db_brand_ids,
                ctx=context,
            )
        resp.latency_ms = int((time.perf_counter() - started) * 1000)
        return resp

    if intent == "favorites_similar":
        resp = _favorites_similar_answer(db, buyer, context)
        resp = _maybe_llm_polish(resp, query=payload.query, buyer=buyer, filters=nlu.filters)
        resp.latency_ms = int((time.perf_counter() - started) * 1000)
        return resp

    if intent == "brand_pick" and nlu.pick_mode and context.last_search_state:
        prev_ids = context.last_search_state.get("related_brand_ids") or []
        resp = _pick_from_previous_brands(
            db,
            buyer,
            brand_ids=prev_ids,
            pick_mode=nlu.pick_mode,
            pick_index=nlu.pick_index,
        )
        resp = _maybe_llm_polish(resp, query=payload.query, buyer=buyer)
        resp.latency_ms = int((time.perf_counter() - started) * 1000)
        return resp

    if intent == "general":
        norm = _normalize(payload.query)
        if any(norm.startswith(g) or norm == g for g in ("tesekkur", "teşekkür", "sagol", "sağol", "eyvallah")):
            answer = "Rica ederim! Başka bir sorunuz olursa buradayım."
        elif any(norm.startswith(g) or norm == g for g in ("merhaba", "selam", "naber", "nasilsin", "nasılsın", "hey", "hello")):
            answer = (
                "Merhaba! FranchiseHub asistanıyım — bütçe, sektör veya şehir söyleyerek "
                "marka önerebilirim. Örnek: «500 bin TL altı gıda» veya «bana uygun marka öner»."
            )
        else:
            answer = (
                "FranchiseHub'da onaylı markaları keşfedebilir, bütçe ve sektörünüze göre "
                "filtreleyebilir ve başvuru oluşturabilirsiniz. "
                "Örnek: «500 bin TL altı gıda markaları» veya «İstanbul'da kahve franchise»."
            )
        return AssistantQueryResponse(
            answer=answer,
            intent="general",
            suggestions=_refine_suggestions(),
            source="rules",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    if intent == "no_match":
        norm = _normalize(payload.query)
        pick_mode = _detect_pick_mode(norm)
        if pick_mode and context.last_search_state:
            prev_ids = context.last_search_state.get("related_brand_ids") or []
            if prev_ids:
                pick_index = _detect_ordinal_index(norm) if pick_mode == "ordinal" else None
                resp = _pick_from_previous_brands(
                    db,
                    buyer,
                    brand_ids=prev_ids,
                    pick_mode=pick_mode,
                    pick_index=pick_index,
                )
                resp = _maybe_llm_polish(resp, query=payload.query, buyer=buyer)
                resp.latency_ms = int((time.perf_counter() - started) * 1000)
                return resp
        brand = _try_resolve_single_brand(db, norm, context.vocabulary)
        if brand and any(h in norm for h in ("hakkinda", "hakkında", "detay", "bilgi", "nedir")):
            resp = _brand_detail_answer(db, buyer, brand.id)
            resp = _maybe_llm_polish(resp, query=payload.query, buyer=buyer)
            resp.latency_ms = int((time.perf_counter() - started) * 1000)
            return resp
        if brand and len(norm.split()) <= 4:
            resp = _brand_detail_answer(db, buyer, brand.id)
            resp = _maybe_llm_polish(resp, query=payload.query, buyer=buyer)
            resp.latency_ms = int((time.perf_counter() - started) * 1000)
            return resp
        if any(h in norm for h in ("oner", "öner", "tavsiye", "uygun")):
            nlu = parse_agent_query(
                payload.query,
                buyer,
                previous_search=context.last_search_state,
                vocabulary=context.vocabulary,
            )
            nlu.intent = "brand_search"
            nlu.filters.use_profile_budget = True
            nlu.filters.max_cost = float(buyer.investment_budget)
            if buyer.preferred_sector and not nlu.filters.sector:
                nlu.filters.sector = buyer.preferred_sector
                nlu.filters.use_profile_sector = True
            brands, brand_ids = _search_brands_for_agent(db, buyer, nlu.filters, context)
            if brands:
                resp = AssistantQueryResponse(
                    answer=_build_brand_search_answer(
                        filters=nlu.filters, buyer=buyer, count=len(brands)
                    ),
                    intent="brand_search",
                    suggestions=_default_suggestions(brands),
                    related_brands=brands,
                    related_brand_ids=brand_ids,
                    filters_applied=filters_applied_dict(nlu.filters),
                    source="rules",
                )
                resp = _maybe_llm_polish(resp, query=payload.query, buyer=buyer, filters=nlu.filters)
                resp.latency_ms = int((time.perf_counter() - started) * 1000)
                return resp

        if any(h in norm for h in ("tesekkur", "teşekkür", "sagol", "sağol", "eyvallah", "tamam")):
            return AssistantQueryResponse(
                answer="Rica ederim! Başka bir sorunuz olursa buradayım.",
                intent="general",
                suggestions=_refine_suggestions(),
                source="rules",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        profile_filters = build_profile_recommendation_filters(buyer)
        brands, brand_ids, used_filters = _search_with_relaxed_filters(
            db, buyer, profile_filters, context
        )
        if brands and len(norm.split()) >= 2:
            resp = AssistantQueryResponse(
                answer=(
                    "Tam eşleşme bulamadım; profilinize yakın "
                    + _build_brand_search_answer(filters=used_filters, buyer=buyer, count=len(brands))
                ),
                intent="brand_search",
                suggestions=_default_suggestions(brands),
                related_brands=brands,
                related_brand_ids=brand_ids,
                filters_applied=filters_applied_dict(used_filters),
                source="rules",
            )
            resp = _maybe_llm_polish(resp, query=payload.query, buyer=buyer, filters=used_filters)
            resp.latency_ms = int((time.perf_counter() - started) * 1000)
            return resp

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

    if nlu.db_brand_ids:
        brands, brand_ids = _search_brands_by_ids(
            db, buyer, nlu.db_brand_ids, context, nlu.filters
        )
        used_filters = nlu.filters
        if not brands:
            brands, brand_ids, used_filters = _search_with_relaxed_filters(
                db, buyer, nlu.filters, context
            )
    else:
        brands, brand_ids, used_filters = _search_with_relaxed_filters(
            db, buyer, nlu.filters, context
        )
    # Semantik (pgvector) fallback: kural/DB araması boş kaldıysa VEYA serbest
    # metin (q) gevşetilip alakasız genel listeye düşüldüyse semantik dene.
    semantic_used = False
    q_relaxed = bool(nlu.filters.q) and not used_filters.q
    if not brands or q_relaxed:
        sem_ids = semantic_brand_search(
            db,
            payload.query,
            location=nlu.filters.location,
            min_cost=nlu.filters.min_cost,
            max_cost=nlu.filters.max_cost,
            limit=AGENT_RESULT_LIMIT,
        )
        if sem_ids:
            sem_brands, sem_brand_ids = _search_brands_by_ids(
                db, buyer, sem_ids, context, nlu.filters
            )
            if sem_brands:
                brands, brand_ids = sem_brands, sem_brand_ids
                semantic_used = True

    # Kullanıcının istediği sektör/anahtar kelime gevşetildiyse dürüstçe belirt.
    relaxed_note = ""
    if semantic_used:
        relaxed_note = "Tam eşleşme bulamadım ama anlamca yakın markalar buldum. "
    elif brands:
        relaxed_note = _build_relaxed_search_note(
            nlu.filters, used_filters, brands=brands
        )
    if relaxed_note:
        answer = f"{relaxed_note} {len(brands)} marka listeliyorum:"
    else:
        answer = _build_brand_search_answer(
            filters=used_filters, buyer=buyer, count=len(brands)
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
        filters_applied=filters_applied_dict(used_filters),
        source="semantic" if semantic_used else "rules",
    )
    resp = _maybe_llm_polish(resp, query=payload.query, buyer=buyer, filters=used_filters)
    resp.latency_ms = int((time.perf_counter() - started) * 1000)
    return resp

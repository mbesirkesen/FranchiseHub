from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from .agent_context import AgentBuyerContext
from .agent_nlu import (
    AgentSearchFilters,
    _normalize,
    _parse_money_tl,
    filters_applied_dict,
)
from .models import Buyer
from .schemas import AssistantQueryRequest, AssistantQueryResponse, AssistantSuggestion

_log = logging.getLogger("franchisehub.agent.tools")


def execute_agent_tool(
    db: Session,
    buyer: Buyer,
    ctx: AgentBuyerContext,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    original_query: str,
) -> Optional[AssistantQueryResponse]:
    """LLM'in seçtiği tool'u çalıştır — sonuç DB'den."""
    from . import buyer_assistant as ba

    try:
        if tool_name == "search_brands":
            return _tool_search_brands(db, buyer, ctx, arguments, ba, original_query)
        if tool_name == "compare_brands":
            names = arguments.get("brand_names") or []
            if not isinstance(names, list) or len(names) < 2:
                return None
            resp = ba._compare_answer(
                db, buyer, [str(n) for n in names[:4]], ctx=ctx
            )
            resp.source = "llm_tools"
            return resp
        if tool_name == "get_application_status":
            resp = ba._application_status_answer(db, buyer)
            resp.source = "llm_tools"
            return resp
        if tool_name == "favorites_similar":
            resp = ba._favorites_similar_answer(db, buyer, ctx)
            resp.source = "llm_tools"
            return ba._maybe_llm_polish(resp, query=original_query, buyer=buyer)
        if tool_name == "pick_from_list":
            return _tool_pick_from_list(db, buyer, ctx, arguments, ba)
        if tool_name == "get_brand_detail":
            return _tool_brand_detail(db, buyer, ctx, arguments, ba)
        if tool_name == "general_help":
            return _tool_general_help(arguments)
    except Exception as exc:
        _log.warning("tool %s failed: %s", tool_name, exc)
    return None


def _mentioned_in_query(value: str, norm_query: str, ctx: AgentBuyerContext) -> bool:
    """LLM, profil sektörü/şehrini filtreye sızdırabilir. Sadece kullanıcının
    açıkça yazdığı sektör/şehri kabul et."""
    norm_value = _normalize(value).strip()
    if not norm_value:
        return False
    # Tam veya kelime bazlı eşleşme: "gida" sorguda geçiyor mu?
    if norm_value in norm_query:
        return True
    for token in norm_value.split():
        if len(token) >= 3 and token in norm_query:
            return True
    return False


def _sanitize_money(value: Any, original_query: str) -> Optional[float]:
    """LLM bazen '2.5 milyon'u max_cost=2.5 olarak gönderir. Birim hatasını düzelt."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    if amount <= 0:
        return None
    norm = _normalize(original_query)
    has_million = "milyon" in norm
    has_thousand = "bin" in norm
    # Franchise yatırımı pratikte >= 10.000 TL; daha küçükse birim düşürülmüş demek
    if amount < 1000 and has_million:
        amount *= 1_000_000
    elif amount < 1000 and has_thousand:
        amount *= 1_000
    elif amount < 1000:
        # Birim ipucu yok ama değer franchise için anlamsız küçük → milyon varsay
        amount *= 1_000_000
    return amount


def _tool_search_brands(
    db: Session,
    buyer: Buyer,
    ctx: AgentBuyerContext,
    args: dict[str, Any],
    ba: Any,
    original_query: str,
) -> AssistantQueryResponse:
    norm_q = _normalize(original_query)

    filters = AgentSearchFilters()
    if args.get("sector") and _mentioned_in_query(str(args["sector"]), norm_q, ctx):
        filters.sector = str(args["sector"])
    if args.get("location") and _mentioned_in_query(str(args["location"]), norm_q, ctx):
        filters.location = str(args["location"])
    if args.get("max_cost") is not None:
        filters.max_cost = _sanitize_money(args["max_cost"], original_query)
    if args.get("min_cost") is not None:
        filters.min_cost = _sanitize_money(args["min_cost"], original_query)
    if args.get("query_text"):
        filters.q = str(args["query_text"])[:100]
    if args.get("sort") in ("cost_asc", "cost_desc", "roi_desc"):
        filters.sort = str(args["sort"])

    # LLM para birimini (milyon/bin) sık karıştırıyor; orijinal sorgudan kural
    # parser ile doğrula. Kural parser milyon/bin ölçeklemesini güvenilir yapar.
    rule_min, rule_max = _parse_money_tl(original_query)
    if rule_max is not None:
        filters.max_cost = rule_max
    if rule_min is not None:
        filters.min_cost = rule_min

    # Profil bütçesini SADECE sorguda gerçek bir bütçe/öneri sinyali varsa uygula.
    # LLM bazen alakasız sorgularda use_profile_budget=true gönderiyor; bayrağına
    # körü körüne güvenme.
    budget_signal = any(
        kw in norm_q
        for kw in ("butce", "butcem", "butceme", "bana uygun", "bana gore", "oner", "öner", "tavsiye")
    )
    if budget_signal and filters.max_cost is None and filters.min_cost is None:
        filters.use_profile_budget = True
        filters.max_cost = float(buyer.investment_budget)

    brands, brand_ids, used = ba._search_with_relaxed_filters(db, buyer, filters, ctx)

    # Semantik (pgvector) fallback: boş kaldıysa VEYA serbest metin (q)
    # gevşetilip alakasız genel listeye düşüldüyse semantik dene.
    semantic_used = False
    q_relaxed = bool(filters.q) and not used.q
    if not brands or q_relaxed:
        from .brand_vector_search import semantic_brand_search

        sem_ids = semantic_brand_search(
            db,
            original_query,
            location=filters.location,
            min_cost=filters.min_cost,
            max_cost=filters.max_cost,
            limit=4,
        )
        if sem_ids:
            sem_brands, sem_brand_ids = ba._search_brands_by_ids(
                db, buyer, sem_ids, ctx, filters
            )
            if sem_brands:
                brands, brand_ids = sem_brands, sem_brand_ids
                semantic_used = True

    answer = ba._build_brand_search_answer(filters=used, buyer=buyer, count=len(brands))
    if semantic_used:
        answer = "Tam eşleşme bulamadım ama anlamca yakın markalar buldum. " + answer
    suggestions = ba._default_suggestions(brands) if brands else ba._refine_suggestions()
    resp = AssistantQueryResponse(
        answer=answer,
        intent="brand_search",
        suggestions=suggestions,
        related_brands=brands,
        related_brand_ids=brand_ids,
        filters_applied=filters_applied_dict(used),
        source="semantic" if semantic_used else "llm_tools",
    )
    return ba._maybe_llm_polish(resp, query=original_query, buyer=buyer, filters=used)


def _tool_pick_from_list(
    db: Session,
    buyer: Buyer,
    ctx: AgentBuyerContext,
    args: dict[str, Any],
    ba: Any,
) -> Optional[AssistantQueryResponse]:
    state = ctx.last_search_state or ctx.session_snapshot
    ids: list[int] = []
    if state:
        ids = state.get("related_brand_ids") or []
    if not ids:
        return None
    mode = str(args.get("mode") or "cheapest")
    pick_index = args.get("index")
    if mode == "ordinal" and pick_index is not None:
        pick_index = int(pick_index)
    resp = ba._pick_from_previous_brands(
        db,
        buyer,
        brand_ids=ids,
        pick_mode=mode,
        pick_index=pick_index if mode == "ordinal" else None,
    )
    resp.source = "llm_tools"
    return ba._maybe_llm_polish(resp, query=str(args), buyer=buyer)


def _tool_brand_detail(
    db: Session,
    buyer: Buyer,
    ctx: AgentBuyerContext,
    args: dict[str, Any],
    ba: Any,
) -> Optional[AssistantQueryResponse]:
    brand_id = args.get("brand_id")
    if brand_id is not None:
        resp = ba._brand_detail_answer(db, buyer, int(brand_id))
        resp.source = "llm_tools"
        return ba._maybe_llm_polish(resp, query=str(args), buyer=buyer)
    name = args.get("brand_name")
    from .agent_nlu import _normalize

    if name and ctx.vocabulary:
        matched = ctx.vocabulary.match_brand_ids(_normalize(str(name)), limit=1)
        if matched:
            resp = ba._brand_detail_answer(db, buyer, matched[0])
            resp.source = "llm_tools"
            return ba._maybe_llm_polish(resp, query=str(args), buyer=buyer)
    if name:
        resolved = ba._resolve_brands_by_names(db, [str(name)])
        if len(resolved) == 1:
            resp = ba._brand_detail_answer(db, buyer, resolved[0].id)
            resp.source = "llm_tools"
            return ba._maybe_llm_polish(resp, query=str(args), buyer=buyer)
    return None


def _tool_general_help(args: dict[str, Any]) -> AssistantQueryResponse:
    tone = str(args.get("tone") or "help")
    if tone == "greeting":
        answer = (
            "Merhaba! Bütçe, sektör veya şehir söyleyerek marka önerebilirim. "
            "Örnek: «500 bin TL altı gıda» veya «bana uygun marka öner»."
        )
    elif tone == "thanks":
        answer = "Rica ederim! Başka sorunuz olursa buradayım."
    else:
        answer = (
            "FranchiseHub'da marka arayabilir, karşılaştırabilir, favorilere ekleyebilir "
            "ve başvuru durumunuzu sorabilirsiniz."
        )
    return AssistantQueryResponse(
        answer=answer,
        intent="general",
        suggestions=[
            AssistantSuggestion(label="Bütçe belirt (ör. 500 bin TL)", action="refine_search"),
            AssistantSuggestion(label="Sektör belirt (gıda, kahve)", action="refine_search"),
        ],
        source="llm_tools",
    )


def parse_tool_arguments(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}

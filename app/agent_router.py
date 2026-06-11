from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Optional

from sqlalchemy.orm import Session

from .agent_config import (
    AGENT_LLM_ENABLED,
    AGENT_LLM_ROUTING_ENABLED,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
)
from .agent_context import AgentBuyerContext
from .agent_tool_defs import AGENT_TOOL_DEFINITIONS
from .agent_tool_runner import execute_agent_tool, parse_tool_arguments
from .models import Buyer
from .schemas import AssistantQueryRequest, AssistantQueryResponse

_log = logging.getLogger("franchisehub.agent.router")


def _build_router_context(buyer: Buyer, ctx: AgentBuyerContext) -> str:
    payload: dict = {
        "buyer_budget_tl": float(buyer.investment_budget),
        "buyer_preferred_sector": buyer.preferred_sector,
        "buyer_city": buyer.city,
        "recent_messages": [
            {"role": role, "text": content[:180]}
            for role, content in ctx.recent_turns[-6:]
        ],
    }
    snap = ctx.session_snapshot or ctx.last_search_state
    if snap:
        payload["last_turn"] = {
            "intent": snap.get("intent"),
            "brand_ids": snap.get("related_brand_ids") or [],
            "filters": snap.get("filters_applied") or {},
        }
    if ctx.vocabulary:
        payload["db_sectors"] = ctx.vocabulary.sectors[:25]
        payload["sample_brands"] = [name for _, name in ctx.vocabulary.brand_entries[:12]]
    return json.dumps(payload, ensure_ascii=False)


def try_llm_tool_route(
    db: Session,
    buyer: Buyer,
    payload: AssistantQueryRequest,
    ctx: AgentBuyerContext,
) -> Optional[AssistantQueryResponse]:
    """
    LLM tool routing — niyet seçimi LLM'de, veri her zaman tool → DB.
    Başarısızsa None döner (kural tabanlı NLU devreye girer).
    """
    if not AGENT_LLM_ROUTING_ENABLED or not AGENT_LLM_ENABLED or not OPENAI_API_KEY:
        return None

    system = (
        "Sen FranchiseHub alıcı asistanısın. Kullanıcı sorusunu anla ve TAM OLARAK BİR tool çağır. "
        "Fiyat, marka listesi veya ROI uydurma — yalnızca tool sonuçlarına güven. "
        "Son listeden seçim (en ucuz hangisi) için pick_from_list kullan. "
        "Selam/teşekkür için general_help. Başvuru için get_application_status. "
        "Karşılaştırma için compare_brands. Marka arama için search_brands. "
        "DB sektör ve örnek marka adları context'te verilir.\n"
        "PARA KURALI: Tutarları TAM TL olarak ver. '2.5 milyon' = 2500000, '500 bin' = 500000. "
        "ASLA 2.5 veya 500 gibi kısaltma gönderme.\n"
        "FİLTRE KURALI: sector ve location parametrelerini SADECE kullanıcı mesajında "
        "açıkça yazdıysa doldur. Kullanıcının profil sektörü/şehri context'te olsa bile, "
        "kullanıcı yazmadıkça bunları filtreye EKLEME. "
        "'bütçeme uygun' denirse use_profile_budget=true ver, max_cost verme."
    )
    user_content = json.dumps(
        {
            "query": payload.query[:500],
            "context": json.loads(_build_router_context(buyer, ctx)),
        },
        ensure_ascii=False,
    )

    try:
        body = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "tools": AGENT_TOOL_DEFINITIONS,
            "tool_choice": "auto",
            "temperature": 0.1,
            "max_tokens": 400,
        }
        req = urllib.request.Request(
            f"{OPENAI_BASE_URL}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
                "User-Agent": "FranchiseHub-Agent/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=18) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8", errors="replace")[:300]
        except OSError:
            pass
        _log.warning("LLM router HTTP %s: %s", exc.code, err_body or exc.reason)
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        _log.warning("LLM router failed: %s", exc)
        return None

    message = data.get("choices", [{}])[0].get("message", {})
    tool_calls = message.get("tool_calls") or []
    if not tool_calls:
        _log.info("LLM router: no tool call, fallback rules")
        return None

    call = tool_calls[0]
    fn = call.get("function") or {}
    tool_name = fn.get("name")
    if not tool_name:
        return None

    args = parse_tool_arguments(fn.get("arguments") or "{}")
    _log.info("LLM router tool=%s args=%s", tool_name, list(args.keys()))

    result = execute_agent_tool(
        db,
        buyer,
        ctx,
        tool_name=tool_name,
        arguments=args,
        original_query=payload.query,
    )
    if result is None:
        _log.info("LLM router tool %s returned None, fallback rules", tool_name)
    return result

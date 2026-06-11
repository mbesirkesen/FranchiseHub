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
from .agent_tool_runner import parse_tool_arguments
from .fo_agent_context import AgentOwnerContext
from .fo_agent_tool_defs import FO_AGENT_TOOL_DEFINITIONS
from .fo_agent_tool_runner import execute_fo_agent_tool
from .models import Brand, FranchiseOwner
from .schemas import AssistantQueryRequest, AssistantQueryResponse

_log = logging.getLogger("franchisehub.agent.fo.router")


def _build_fo_router_context(db: Session, owner: FranchiseOwner, ctx: AgentOwnerContext) -> str:
    from sqlalchemy import select

    brand = db.scalar(
        select(Brand).where(Brand.franchise_owner_id == owner.id).order_by(Brand.id.asc())
    )
    payload: dict = {
        "owner_city": owner.city,
        "brand_name": brand.name if brand else None,
        "recent_messages": [
            {"role": role, "text": content[:180]}
            for role, content in ctx.recent_turns[-6:]
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def try_llm_fo_tool_route(
    db: Session,
    owner: FranchiseOwner,
    payload: AssistantQueryRequest,
    ctx: AgentOwnerContext,
) -> Optional[AssistantQueryResponse]:
    if not AGENT_LLM_ROUTING_ENABLED or not AGENT_LLM_ENABLED or not OPENAI_API_KEY:
        return None

    system = (
        "Sen FranchiseHub franchise sahibi (FO) asistanısın. Kullanıcı sorusunu anla ve "
        "TAM OLARAK BİR tool çağır. Stok, tedarik ve başvuru sayılarını uydurma — yalnızca tool. "
        "Düşük stok için get_low_stock. Tedarik için list_supply_requests. "
        "Bekleyen başvuru için list_pending_applications. Özet için owner_dashboard_summary. "
        "Şubeler için list_my_outlets. Selam/teşekkür için fo_general_help."
    )
    user_content = json.dumps(
        {
            "query": payload.query[:500],
            "context": json.loads(_build_fo_router_context(db, owner, ctx)),
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
            "tools": FO_AGENT_TOOL_DEFINITIONS,
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
        _log.warning("FO LLM router HTTP %s: %s", exc.code, err_body or exc.reason)
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        _log.warning("FO LLM router failed: %s", exc)
        return None

    message = data.get("choices", [{}])[0].get("message", {})
    tool_calls = message.get("tool_calls") or []
    if not tool_calls:
        _log.info("FO LLM router: no tool call, fallback rules")
        return None

    call = tool_calls[0]
    fn = call.get("function") or {}
    tool_name = fn.get("name")
    if not tool_name:
        return None

    args = parse_tool_arguments(fn.get("arguments") or "{}")
    _log.info("FO LLM router tool=%s args=%s", tool_name, list(args.keys()))

    result = execute_fo_agent_tool(
        db,
        owner.id,
        ctx,
        tool_name=tool_name,
        arguments=args,
        original_query=payload.query,
    )
    if result is None:
        _log.info("FO LLM router tool %s returned None, fallback rules", tool_name)
    return result

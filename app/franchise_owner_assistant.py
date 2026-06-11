from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from .fo_agent_context import AgentOwnerContext
from .fo_agent_nlu import classify_fo_query
from .fo_agent_router import try_llm_fo_tool_route
from .fo_agent_tool_runner import execute_fo_agent_tool
from .models import FranchiseOwner
from .schemas import AssistantQueryRequest, AssistantQueryResponse, AssistantSuggestion

_log = logging.getLogger("franchisehub.agent.fo")


def load_owner_context(db: Session, owner_id: int) -> AgentOwnerContext:
    return AgentOwnerContext(owner_id=owner_id)


def answer_franchise_owner_assistant(
    db: Session,
    owner: FranchiseOwner,
    payload: AssistantQueryRequest,
    ctx: Optional[AgentOwnerContext] = None,
) -> AssistantQueryResponse:
    ctx = ctx or load_owner_context(db, owner.id)

    routed = try_llm_fo_tool_route(db, owner, payload, ctx)
    if routed is not None:
        routed.source = routed.source or "llm_tools"
        return routed

    nlu = classify_fo_query(payload.query)
    if nlu is not None:
        tool_resp = execute_fo_agent_tool(
            db,
            owner.id,
            ctx,
            tool_name=nlu.tool_name,
            arguments=nlu.arguments,
            original_query=payload.query,
        )
        if tool_resp is not None:
            tool_resp.source = "rules"
            return tool_resp

    return AssistantQueryResponse(
        answer=(
            "Sorunuzu tam anlayamadım. Düşük stok, tedarik talepleri, bekleyen başvurular "
            "veya panel özeti hakkında sorabilirsiniz."
        ),
        intent="no_match",
        suggestions=[
            AssistantSuggestion(label="Düşük stoklar", action="low_stock"),
            AssistantSuggestion(label="Bekleyen başvurular", action="pending_applications"),
            AssistantSuggestion(label="Panel özeti", action="dashboard"),
        ],
        source="rules",
    )

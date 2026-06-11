from __future__ import annotations

import logging
import time

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .agent_config import AGENT_CONTEXT_MESSAGE_LIMIT
from .agent_metrics import record_agent_turn
from .agent_rate_limit import check_agent_rate_limit
from .agent_sanitize import sanitize_agent_query
from .agent_session_store import (
    append_message,
    create_session_for_owner,
    get_session_for_owner,
    recent_turns,
)
from .fo_agent_context import AgentOwnerContext
from .franchise_owner_assistant import answer_franchise_owner_assistant, load_owner_context
from .models import AgentMessageRole, FranchiseOwner
from .schemas import AssistantChatRequest, AssistantQueryRequest, AssistantQueryResponse

_log = logging.getLogger("franchisehub.agent.fo")


def _mask_query(query: str) -> str:
    if len(query) <= 80:
        return query
    return query[:77] + "..."


def run_fo_agent_turn(
    db: Session,
    owner: FranchiseOwner,
    payload: AssistantChatRequest,
) -> AssistantQueryResponse:
    check_agent_rate_limit(f"fo:{owner.id}")
    try:
        return _run_fo_agent_turn_inner(db, owner, payload)
    except Exception:
        db.rollback()
        raise


def _run_fo_agent_turn_inner(
    db: Session,
    owner: FranchiseOwner,
    payload: AssistantChatRequest,
) -> AssistantQueryResponse:
    query = sanitize_agent_query(payload.query)
    if len(query) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="query en az 2 karakter olmalı",
        )

    req = AssistantQueryRequest(query=query, session_id=payload.session_id)

    if payload.session_id and not payload.new_session:
        session = get_session_for_owner(db, payload.session_id, owner.id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    else:
        session = create_session_for_owner(db, owner_id=owner.id, title=query[:200])

    ctx: AgentOwnerContext = load_owner_context(db, owner.id)
    ctx.recent_turns = recent_turns(db, session.id, AGENT_CONTEXT_MESSAGE_LIMIT)

    append_message(
        db,
        session=session,
        role=AgentMessageRole.user,
        content=query,
    )

    t0 = time.perf_counter()
    response = answer_franchise_owner_assistant(db, owner, req, ctx)
    latency = int((time.perf_counter() - t0) * 1000)
    if response.latency_ms is None:
        response.latency_ms = latency

    assistant_msg = append_message(
        db,
        session=session,
        role=AgentMessageRole.assistant,
        content=response.answer,
        intent=response.intent,
        source=response.source,
        filters_applied=response.filters_applied,
        related_brand_ids=response.related_brand_ids,
        latency_ms=response.latency_ms,
    )

    response.session_id = session.id
    response.message_id = assistant_msg.id

    record_agent_turn(
        intent=response.intent,
        source=response.source,
        query=query,
        brand_count=0,
    )
    _log.info(
        "fo_agent_turn owner_id=%s session_id=%s intent=%s source=%s latency_ms=%s query=%s",
        owner.id,
        session.id,
        response.intent,
        response.source,
        response.latency_ms,
        _mask_query(query),
    )

    db.commit()
    return response


def run_fo_agent_query_only(
    db: Session,
    owner: FranchiseOwner,
    payload: AssistantQueryRequest,
) -> AssistantQueryResponse:
    check_agent_rate_limit(f"fo:{owner.id}")
    query = sanitize_agent_query(payload.query)
    req = AssistantQueryRequest(query=query)
    ctx = load_owner_context(db, owner.id)
    response = answer_franchise_owner_assistant(db, owner, req, ctx)
    record_agent_turn(
        intent=response.intent,
        source=response.source,
        query=query,
        brand_count=0,
    )
    _log.info(
        "fo_agent_query owner_id=%s intent=%s source=%s",
        owner.id,
        response.intent,
        response.source,
    )
    db.commit()
    return response

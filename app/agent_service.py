from __future__ import annotations

import logging
import time

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .agent_config import AGENT_CONTEXT_MESSAGE_LIMIT
from .agent_context import load_buyer_context
from .agent_rate_limit import check_agent_rate_limit
from .agent_sanitize import sanitize_agent_query
from .agent_session_store import (
    append_message,
    create_session,
    get_session_for_buyer,
    last_brand_search_state,
    recent_turns,
)
from .buyer_assistant import answer_buyer_assistant
from .models import AgentMessageRole, Buyer
from .schemas import AssistantChatRequest, AssistantQueryRequest, AssistantQueryResponse

_log = logging.getLogger("franchisehub.agent")


def _mask_query(query: str) -> str:
    if len(query) <= 80:
        return query
    return query[:77] + "..."


def run_agent_turn(
    db: Session,
    buyer: Buyer,
    payload: AssistantChatRequest,
) -> AssistantQueryResponse:
    check_agent_rate_limit(buyer.id)

    try:
        return _run_agent_turn_inner(db, buyer, payload)
    except Exception:
        db.rollback()
        raise


def _run_agent_turn_inner(
    db: Session,
    buyer: Buyer,
    payload: AssistantChatRequest,
) -> AssistantQueryResponse:
    query = sanitize_agent_query(payload.query)
    if len(query) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="query en az 2 karakter olmalı",
        )

    req = AssistantQueryRequest(
        query=query,
        brand_id=payload.brand_id,
        brand_context_id=payload.brand_context_id,
        session_id=payload.session_id,
    )

    if payload.session_id and not payload.new_session:
        session = get_session_for_buyer(db, payload.session_id, buyer.id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    else:
        session = create_session(
            db,
            buyer_id=buyer.id,
            title=query[:200],
            brand_context_id=payload.brand_context_id or payload.brand_id,
        )

    ctx = load_buyer_context(db, buyer)
    if session:
        ctx.recent_turns = recent_turns(db, session.id, AGENT_CONTEXT_MESSAGE_LIMIT)
        ctx.last_search_state = last_brand_search_state(db, session.id)

    append_message(
        db,
        session=session,
        role=AgentMessageRole.user,
        content=query,
    )

    t0 = time.perf_counter()
    response = answer_buyer_assistant(db, buyer, req, ctx)
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

    _log.info(
        "agent_turn buyer_id=%s session_id=%s intent=%s source=%s brands=%s latency_ms=%s query=%s",
        buyer.id,
        session.id,
        response.intent,
        response.source,
        len(response.related_brand_ids),
        response.latency_ms,
        _mask_query(query),
    )

    db.commit()
    return response


def run_agent_query_only(
    db: Session,
    buyer: Buyer,
    payload: AssistantQueryRequest,
) -> AssistantQueryResponse:
    """Stateless — oturum kaydı yok; POST /agent/query için."""
    check_agent_rate_limit(buyer.id)
    query = sanitize_agent_query(payload.query)
    req = AssistantQueryRequest(
        query=query,
        brand_id=payload.brand_id,
        brand_context_id=payload.brand_context_id,
    )
    ctx = load_buyer_context(db, buyer)
    response = answer_buyer_assistant(db, buyer, req, ctx)
    _log.info(
        "agent_query buyer_id=%s intent=%s source=%s latency_ms=%s",
        buyer.id,
        response.intent,
        response.source,
        response.latency_ms,
    )
    db.commit()
    return response

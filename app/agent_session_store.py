from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .agent_config import AGENT_SESSION_MAX_MESSAGES
from .models import AgentMessage, AgentMessageRole, AgentSession
from .schemas import AgentMessageRead, AgentSessionRead


def _json_dict(value: Any) -> Optional[dict]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _json_list(value: Any) -> Optional[list]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, list) else None
    return None


def create_session(
    db: Session,
    *,
    buyer_id: int,
    title: Optional[str] = None,
    brand_context_id: Optional[int] = None,
) -> AgentSession:
    session = AgentSession(
        buyer_id=buyer_id,
        title=(title or "Yeni sohbet")[:200],
        brand_context_id=brand_context_id,
    )
    db.add(session)
    db.flush()
    return session


def create_session_for_owner(
    db: Session,
    *,
    owner_id: int,
    title: Optional[str] = None,
) -> AgentSession:
    session = AgentSession(
        franchise_owner_id=owner_id,
        title=(title or "Yeni sohbet")[:200],
    )
    db.add(session)
    db.flush()
    return session


def get_session_for_buyer(db: Session, session_id: int, buyer_id: int) -> Optional[AgentSession]:
    return db.scalar(
        select(AgentSession).where(
            AgentSession.id == session_id,
            AgentSession.buyer_id == buyer_id,
        )
    )


def get_session_for_owner(
    db: Session, session_id: int, owner_id: int
) -> Optional[AgentSession]:
    return db.scalar(
        select(AgentSession).where(
            AgentSession.id == session_id,
            AgentSession.franchise_owner_id == owner_id,
        )
    )


def touch_session(db: Session, session: AgentSession) -> None:
    session.updated_at = datetime.utcnow()


def append_message(
    db: Session,
    *,
    session: AgentSession,
    role: AgentMessageRole,
    content: str,
    intent: Optional[str] = None,
    source: str = "rules",
    filters_applied: Optional[dict] = None,
    related_brand_ids: Optional[list[int]] = None,
    latency_ms: Optional[int] = None,
) -> AgentMessage:
    count = int(
        db.scalar(
            select(func.count(AgentMessage.id)).where(AgentMessage.session_id == session.id)
        )
        or 0
    )
    if count >= AGENT_SESSION_MAX_MESSAGES:
        raise ValueError("session_message_limit")

    msg = AgentMessage(
        session_id=session.id,
        role=role.value,
        content=content,
        intent=intent,
        source=source,
        filters_applied=filters_applied,
        related_brand_ids=related_brand_ids,
        latency_ms=latency_ms,
    )
    db.add(msg)
    touch_session(db, session)
    if role == AgentMessageRole.user and (not session.title or session.title == "Yeni sohbet"):
        session.title = content[:200]
    db.flush()
    return msg


def load_session_snapshot(db: Session, session_id: int) -> Optional[dict]:
    """Son asistan turlarından bağlam: liste, karşılaştırma, filtreler."""
    rows = db.scalars(
        select(AgentMessage)
        .where(
            AgentMessage.session_id == session_id,
            AgentMessage.role == AgentMessageRole.assistant.value,
        )
        .order_by(AgentMessage.created_at.desc())
        .limit(10)
    ).all()

    last_list: Optional[dict] = None
    last_compare_ids: list[int] = []
    last_intent: Optional[str] = None
    last_brand_id: Optional[int] = None

    for row in rows:
        related = _json_list(row.related_brand_ids) or []
        filters = _json_dict(row.filters_applied) or {}
        if not last_intent:
            last_intent = row.intent
        if related and last_list is None:
            last_list = {
                "filters_applied": filters,
                "related_brand_ids": related,
                "intent": row.intent,
            }
            last_brand_id = related[0]
        if row.intent == "brand_compare" and related and not last_compare_ids:
            last_compare_ids = related
        if last_list and last_compare_ids:
            break

    if not last_list and not last_compare_ids:
        return None

    return {
        "filters_applied": (last_list or {}).get("filters_applied") or {},
        "related_brand_ids": (last_list or {}).get("related_brand_ids") or [],
        "intent": (last_list or {}).get("intent") or last_intent,
        "compare_brand_ids": last_compare_ids,
        "last_brand_id": last_brand_id,
    }


def last_brand_search_state(db: Session, session_id: int) -> Optional[dict]:
    """Son marka listesi dönen tur — takip soruları (en ucuz hangisi vb.) için."""
    rows = db.scalars(
        select(AgentMessage)
        .where(
            AgentMessage.session_id == session_id,
            AgentMessage.role == AgentMessageRole.assistant.value,
        )
        .order_by(AgentMessage.created_at.desc())
        .limit(8)
    ).all()
    for row in rows:
        related_brand_ids = _json_list(row.related_brand_ids) or []
        if not related_brand_ids:
            continue
        filters_applied = _json_dict(row.filters_applied) or {}
        return {
            "filters_applied": filters_applied,
            "related_brand_ids": related_brand_ids,
            "intent": row.intent,
        }
    return None


def recent_turns(db: Session, session_id: int, limit: int) -> list[tuple[str, str]]:
    rows = db.scalars(
        select(AgentMessage)
        .where(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.created_at.desc())
        .limit(limit)
    ).all()
    turns: list[tuple[str, str]] = []
    for row in reversed(rows):
        turns.append((row.role, row.content))
    return turns


def list_sessions(db: Session, buyer_id: int, *, limit: int = 20) -> list[AgentSessionRead]:
    sessions = db.scalars(
        select(AgentSession)
        .where(AgentSession.buyer_id == buyer_id)
        .order_by(AgentSession.updated_at.desc())
        .limit(limit)
    ).all()
    out: list[AgentSessionRead] = []
    for s in sessions:
        msg_count = int(
            db.scalar(
                select(func.count(AgentMessage.id)).where(AgentMessage.session_id == s.id)
            )
            or 0
        )
        last = db.scalar(
            select(AgentMessage)
            .where(AgentMessage.session_id == s.id)
            .order_by(AgentMessage.created_at.desc())
            .limit(1)
        )
        preview = last.content[:120] if last else None
        out.append(
            AgentSessionRead(
                id=s.id,
                title=s.title,
                brand_context_id=s.brand_context_id,
                created_at=s.created_at,
                updated_at=s.updated_at,
                message_count=msg_count,
                last_message_preview=preview,
            )
        )
    return out


def session_messages(db: Session, session_id: int, buyer_id: int) -> list[AgentMessageRead]:
    session = get_session_for_buyer(db, session_id, buyer_id)
    if not session:
        return []
    rows = db.scalars(
        select(AgentMessage)
        .where(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.created_at.asc())
    ).all()
    return [
        AgentMessageRead(
            id=m.id,
            session_id=m.session_id,
            role=m.role,
            content=m.content,
            intent=m.intent,
            source=m.source,
            filters_applied=_json_dict(m.filters_applied),
            related_brand_ids=_json_list(m.related_brand_ids),
            created_at=m.created_at,
        )
        for m in rows
    ]


def delete_session(db: Session, session_id: int, buyer_id: int) -> bool:
    session = get_session_for_buyer(db, session_id, buyer_id)
    if not session:
        return False
    db.delete(session)
    return True


def list_sessions_for_owner(
    db: Session, owner_id: int, *, limit: int = 20
) -> list[AgentSessionRead]:
    sessions = db.scalars(
        select(AgentSession)
        .where(AgentSession.franchise_owner_id == owner_id)
        .order_by(AgentSession.updated_at.desc())
        .limit(limit)
    ).all()
    out: list[AgentSessionRead] = []
    for s in sessions:
        msg_count = int(
            db.scalar(
                select(func.count(AgentMessage.id)).where(AgentMessage.session_id == s.id)
            )
            or 0
        )
        last = db.scalar(
            select(AgentMessage)
            .where(AgentMessage.session_id == s.id)
            .order_by(AgentMessage.created_at.desc())
            .limit(1)
        )
        preview = last.content[:120] if last else None
        out.append(
            AgentSessionRead(
                id=s.id,
                title=s.title,
                brand_context_id=s.brand_context_id,
                created_at=s.created_at,
                updated_at=s.updated_at,
                message_count=msg_count,
                last_message_preview=preview,
            )
        )
    return out


def session_messages_for_owner(
    db: Session, session_id: int, owner_id: int
) -> list[AgentMessageRead]:
    session = get_session_for_owner(db, session_id, owner_id)
    if not session:
        return []
    rows = db.scalars(
        select(AgentMessage)
        .where(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.created_at.asc())
    ).all()
    return [
        AgentMessageRead(
            id=m.id,
            session_id=m.session_id,
            role=m.role,
            content=m.content,
            intent=m.intent,
            source=m.source,
            filters_applied=_json_dict(m.filters_applied),
            related_brand_ids=_json_list(m.related_brand_ids),
            created_at=m.created_at,
        )
        for m in rows
    ]


def delete_session_for_owner(db: Session, session_id: int, owner_id: int) -> bool:
    session = get_session_for_owner(db, session_id, owner_id)
    if not session:
        return False
    db.delete(session)
    return True

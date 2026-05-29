from __future__ import annotations

"""Franchise asistanı — sohbet oturumları ve NLU."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..agent_service import run_agent_query_only, run_agent_turn
from ..agent_session_store import delete_session, list_sessions, session_messages
from ..database import get_db
from ..dependencies import get_current_principal, require_roles
from ..models import Buyer, UserRole
from ..schemas import (
    AgentMessageRead,
    AgentSessionDetailResponse,
    AgentSessionRead,
    AssistantChatRequest,
    AssistantQueryRequest,
    AssistantQueryResponse,
    AuthenticatedPrincipal,
)

router = APIRouter(prefix="/agent", tags=["agent"])


def _get_buyer(db: Session, current_user: AuthenticatedPrincipal) -> Buyer:
    buyer = db.get(Buyer, current_user.user_id)
    if not buyer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Buyer not found")
    return buyer


@router.post(
    "/chat",
    response_model=AssistantQueryResponse,
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def agent_chat(
    payload: AssistantChatRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    """
    Ana sohbet endpoint'i — mesajları oturumda saklar.
    session_id ile devam; yoksa veya new_session=true ile yeni oturum.
    """
    buyer = _get_buyer(db, current_user)
    try:
        return run_agent_turn(db, buyer, payload)
    except ValueError as exc:
        if str(exc) == "session_message_limit":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bu sohbet mesaj limitine ulaştı. Yeni sohbet başlatın.",
            ) from exc
        raise


@router.post(
    "/query",
    response_model=AssistantQueryResponse,
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def agent_query(
    payload: AssistantQueryRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    """Tek tur — oturum kaydı olmadan (frontend geçiş / test)."""
    buyer = _get_buyer(db, current_user)
    return run_agent_query_only(db, buyer, payload)


@router.get(
    "/sessions",
    response_model=list[AgentSessionRead],
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def list_agent_sessions(
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    return list_sessions(db, current_user.user_id)


@router.get(
    "/sessions/{session_id}",
    response_model=AgentSessionDetailResponse,
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def get_agent_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    sessions = list_sessions(db, current_user.user_id, limit=100)
    meta = next((s for s in sessions if s.id == session_id), None)
    if not meta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    messages = session_messages(db, session_id, current_user.user_id)
    return AgentSessionDetailResponse(session=meta, messages=messages)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(UserRole.buyer))],
)
def remove_agent_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    if not delete_session(db, session_id, current_user.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    db.commit()
    return None

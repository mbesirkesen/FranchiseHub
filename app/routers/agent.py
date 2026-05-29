from __future__ import annotations

"""Frontend alias: POST /agent/query → buyer asistan."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..buyer_assistant import answer_buyer_assistant
from ..database import get_db
from ..dependencies import get_current_principal, require_roles
from ..models import Buyer, UserRole
from ..schemas import AssistantQueryRequest, AssistantQueryResponse, AuthenticatedPrincipal

router = APIRouter(prefix="/agent", tags=["agent"])


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
    buyer = db.get(Buyer, current_user.user_id)
    if not buyer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Buyer not found",
        )
    return answer_buyer_assistant(db, buyer, payload)

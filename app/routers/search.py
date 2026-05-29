from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_principal, require_roles
from ..models import UserRole
from ..schemas import AuthenticatedPrincipal, SearchResponse
from ..search_service import platform_search

router = APIRouter(tags=["search"])


@router.get(
    "/search",
    response_model=SearchResponse,
    dependencies=[Depends(require_roles(UserRole.buyer, UserRole.franchise_owner))],
)
def search_platform(
    q: str = Query(..., min_length=2, max_length=120),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    term = q.strip()
    if len(term) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must be at least 2 characters",
        )
    return platform_search(db, current_user, query=term, limit=limit)

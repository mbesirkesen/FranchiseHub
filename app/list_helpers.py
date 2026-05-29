from __future__ import annotations

from typing import Any, Callable, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from .pagination import paginated_meta

T = TypeVar("T")


def paginate_scalars(
    db: Session,
    stmt: Select[Any],
    *,
    page: int,
    page_size: int,
    mapper: Callable[[Any], T],
) -> tuple[list[T], dict[str, int]]:
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int(db.scalar(count_stmt) or 0)
    offset = (page - 1) * page_size
    rows = db.scalars(stmt.offset(offset).limit(page_size)).all()
    return [mapper(row) for row in rows], paginated_meta(total, page, page_size)

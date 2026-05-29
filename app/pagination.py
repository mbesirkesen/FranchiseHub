from __future__ import annotations

import math
from typing import Any, Optional

from pydantic import BaseModel


def total_pages(total: int, page_size: int) -> int:
    if total == 0:
        return 0
    return math.ceil(total / page_size)


class PaginatedMeta(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int


def paginated_meta(total: int, page: int, page_size: int) -> dict[str, int]:
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages(total, page_size),
    }


def apply_pagination(stmt, *, page: int, page_size: int):
    offset = (page - 1) * page_size
    return stmt.offset(offset).limit(page_size)

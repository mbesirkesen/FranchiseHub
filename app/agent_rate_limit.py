from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

from .agent_config import AGENT_RATE_LIMIT_PER_MINUTE

_lock = threading.Lock()
_buckets: dict[int, deque[float]] = defaultdict(deque)


def check_agent_rate_limit(buyer_id: int) -> None:
    """Tek sunucu için sliding window. Çoklu instance için Redis gerekir."""
    now = time.monotonic()
    window = 60.0
    limit = AGENT_RATE_LIMIT_PER_MINUTE

    with _lock:
        bucket = _buckets[buyer_id]
        while bucket and bucket[0] <= now - window:
            bucket.popleft()
        if len(bucket) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Asistan limiti aşıldı. Dakikada en fazla {limit} mesaj gönderebilirsiniz.",
            )
        bucket.append(now)

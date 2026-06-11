from __future__ import annotations

import logging
from collections import Counter
from threading import Lock

_log = logging.getLogger("franchisehub.agent.metrics")

_lock = Lock()
_intent_counts: Counter[str] = Counter()
_no_match_queries: list[str] = []
_MAX_NO_MATCH_STORE = 50


def record_agent_turn(
    *,
    intent: str,
    source: str,
    query: str,
    brand_count: int,
) -> None:
    masked = query if len(query) <= 100 else query[:97] + "..."
    with _lock:
        _intent_counts[f"{intent}:{source}"] += 1
        if intent == "no_match":
            _no_match_queries.append(masked)
            if len(_no_match_queries) > _MAX_NO_MATCH_STORE:
                _no_match_queries.pop(0)
    _log.info(
        "agent_metric intent=%s source=%s brands=%s query=%s",
        intent,
        source,
        brand_count,
        masked,
    )


def snapshot_metrics() -> dict[str, object]:
    with _lock:
        return {
            "intent_source_counts": dict(_intent_counts),
            "recent_no_match": list(_no_match_queries),
        }

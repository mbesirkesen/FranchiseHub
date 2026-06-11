from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentOwnerContext:
    owner_id: int
    recent_turns: list[tuple[str, str]] = field(default_factory=list)
    session_snapshot: Optional[dict] = None

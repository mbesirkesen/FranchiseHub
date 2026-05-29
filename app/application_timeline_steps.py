from __future__ import annotations

from datetime import datetime
from typing import Optional

from .models import Application, ApplicationStatus as DbApplicationStatus
from .schemas import ApplicationTimelineStep, TimelineStepStatus

_STEP_DEFS: list[tuple[str, str]] = [
    ("review", "Ön İnceleme"),
    ("financial", "Finansal İnceleme"),
    ("contract", "Sözleşme"),
    ("onboarding", "Açılış Hazırlığı"),
    ("active", "İşletme"),
]


def build_timeline_steps(
    application: Application,
    *,
    message_count: int,
) -> list[ApplicationTimelineStep]:
    created_at: Optional[datetime] = application.created_at
    statuses: dict[str, TimelineStepStatus] = {
        step_id: TimelineStepStatus.pending for step_id, _ in _STEP_DEFS
    }

    if application.status == DbApplicationStatus.rejected:
        statuses["review"] = TimelineStepStatus.failed
    elif application.status == DbApplicationStatus.pending:
        statuses["review"] = TimelineStepStatus.active
    elif application.status == DbApplicationStatus.approved:
        statuses["review"] = TimelineStepStatus.done
        statuses["financial"] = TimelineStepStatus.done
        if message_count > 0:
            statuses["contract"] = TimelineStepStatus.done
            statuses["onboarding"] = TimelineStepStatus.active
        else:
            statuses["contract"] = TimelineStepStatus.active

    steps: list[ApplicationTimelineStep] = []
    for step_id, label in _STEP_DEFS:
        at = created_at if statuses[step_id] != TimelineStepStatus.pending else None
        steps.append(
            ApplicationTimelineStep(
                id=step_id,
                label=label,
                status=statuses[step_id],
                at=at,
            )
        )
    return steps

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .application_access import require_application_access
from .application_status import resolve_extended_status
from .application_timeline_steps import build_timeline_steps
from .models import Application, ApplicationStatus as DbApplicationStatus, Message, UserRole
from .schemas import (
    ApplicationExtendedStatus,
    ApplicationStatus,
    ApplicationTimelineEvent,
    ApplicationTimelineResponse,
    AuthenticatedPrincipal,
)


def build_application_timeline(
    db: Session,
    application: Application,
    principal: AuthenticatedPrincipal,
) -> ApplicationTimelineResponse:
    require_application_access(db, application, principal)

    message_count = int(
        db.scalar(
            select(func.count(Message.id)).where(
                Message.application_id == application.id
            )
        )
        or 0
    )
    ext_status, ext_label = resolve_extended_status(application, message_count=message_count)

    events: list[ApplicationTimelineEvent] = []
    if application.created_at:
        events.append(
            ApplicationTimelineEvent(
                id=f"app-{application.id}-created",
                event_type="application_created",
                title="Başvuru oluşturuldu",
                description=application.notes,
                occurred_at=application.created_at,
                actor_role=UserRole.buyer,
                status=ApplicationStatus.pending,
                extended_status=ApplicationExtendedStatus.submitted,
            )
        )

    if application.status != DbApplicationStatus.pending:
        status_titles = {
            DbApplicationStatus.approved: "Başvuru onaylandı",
            DbApplicationStatus.rejected: "Başvuru reddedildi",
        }
        events.append(
            ApplicationTimelineEvent(
                id=f"app-{application.id}-status-{application.status.value}",
                event_type="status_changed",
                title=status_titles.get(application.status, "Durum güncellendi"),
                description=application.notes,
                occurred_at=application.created_at,
                actor_role=UserRole.franchise_owner,
                status=ApplicationStatus(application.status.value),
                extended_status=ext_status,
            )
        )

    messages = db.scalars(
        select(Message)
        .where(Message.application_id == application.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    ).all()
    for msg in messages:
        if not msg.created_at:
            continue
        events.append(
            ApplicationTimelineEvent(
                id=f"msg-{msg.id}",
                event_type="message_sent",
                title="Mesaj gönderildi",
                description=msg.content[:200] if msg.content else None,
                occurred_at=msg.created_at,
                actor_role=UserRole(msg.sender_role.value),
                status=ApplicationStatus(application.status.value),
                extended_status=ext_status,
            )
        )

    events.sort(key=lambda e: e.occurred_at or application.created_at)

    steps = build_timeline_steps(application, message_count=message_count)

    return ApplicationTimelineResponse(
        application_id=application.id,
        status=ApplicationStatus(application.status.value),
        extended_status=ext_status,
        extended_status_label=ext_label,
        steps=steps,
        events=events,
    )

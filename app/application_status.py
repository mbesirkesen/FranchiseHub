from __future__ import annotations

from .models import Application, ApplicationStatus as DbApplicationStatus
from .schemas import ApplicationExtendedStatus


def resolve_extended_status(
    app: Application, *, message_count: int
) -> tuple[ApplicationExtendedStatus, str]:
    if app.status == DbApplicationStatus.rejected:
        return ApplicationExtendedStatus.rejected, "Reddedildi"
    if app.status == DbApplicationStatus.approved:
        if message_count > 0:
            return ApplicationExtendedStatus.in_conversation, "Mesajlaşma aktif"
        return ApplicationExtendedStatus.approved, "Onaylandı"
    if message_count > 0:
        return ApplicationExtendedStatus.under_review, "İnceleniyor"
    return ApplicationExtendedStatus.submitted, "Başvuru gönderildi"

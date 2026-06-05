from __future__ import annotations

from sqlalchemy.orm import Session

from .models import (
    Application,
    ApplicationStatus,
    Brand,
    Buyer,
    Inventory,
    Message,
    UserRole,
)
from .notification_service import create_notification


def _buyer_display(buyer: Buyer) -> str:
    return f"{buyer.first_name} {buyer.last_name}".strip()


def notify_new_application(
    db: Session,
    *,
    application: Application,
    brand: Brand,
    buyer: Buyer,
) -> None:
    if not brand.franchise_owner_id:
        return
    create_notification(
        db,
        recipient_role=UserRole.franchise_owner,
        recipient_id=brand.franchise_owner_id,
        title="Yeni başvuru",
        body=f"{_buyer_display(buyer)}, «{brand.name}» markanıza başvurdu.",
        notification_type="application_pending",
        action_url=f"/franchise-owner/applications/{application.id}",
        resource_type="application",
        resource_id=application.id,
    )


def notify_application_status_change(
    db: Session,
    *,
    application: Application,
    brand: Brand,
    buyer: Buyer,
    new_status: ApplicationStatus,
) -> None:
    if new_status == ApplicationStatus.approved:
        title = "Başvurunuz onaylandı"
        body = f"«{brand.name}» başvurunuz onaylandı. Mesajlaşmaya başlayabilirsiniz."
        ntype = "application_approved"
    elif new_status == ApplicationStatus.rejected:
        title = "Başvurunuz reddedildi"
        body = f"«{brand.name}» başvurunuz reddedildi."
        ntype = "application_rejected"
    else:
        return

    create_notification(
        db,
        recipient_role=UserRole.buyer,
        recipient_id=buyer.id,
        title=title,
        body=body,
        notification_type=ntype,
        action_url=f"/buyer/applications/{application.id}",
        resource_type="application",
        resource_id=application.id,
    )


def notify_new_message(
    db: Session,
    *,
    message: Message,
    application: Application,
    brand: Brand,
    buyer: Buyer,
) -> None:
    preview = (message.content or "")[:120]
    if message.sender_role == UserRole.buyer:
        if not brand.franchise_owner_id:
            return
        create_notification(
            db,
            recipient_role=UserRole.franchise_owner,
            recipient_id=brand.franchise_owner_id,
            title="Yeni mesaj",
            body=f"{_buyer_display(buyer)}: {preview}",
            notification_type="message",
            action_url=f"/franchise-owner/messages/{application.id}",
            resource_type="application",
            resource_id=application.id,
        )
    else:
        create_notification(
            db,
            recipient_role=UserRole.buyer,
            recipient_id=buyer.id,
            title="Yeni mesaj",
            body=f"«{brand.name}»: {preview}",
            notification_type="message",
            action_url=f"/buyer/messages/{application.id}",
            resource_type="application",
            resource_id=application.id,
        )


def notify_low_stock(
    db: Session,
    *,
    item: Inventory,
    franchise_owner_id: int,
) -> None:
    create_notification(
        db,
        recipient_role=UserRole.franchise_owner,
        recipient_id=franchise_owner_id,
        title="Düşük stok uyarısı",
        body=(
            f"«{item.item_name}» stok seviyesi {item.stock_level} "
            f"(eşik: {item.low_stock_threshold})."
        ),
        notification_type="stock",
        action_url="/franchise-owner/stock",
        resource_type="inventory",
        resource_id=item.id,
    )

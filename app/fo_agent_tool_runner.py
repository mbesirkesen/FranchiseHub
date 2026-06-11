from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .fo_agent_context import AgentOwnerContext
from .inventory_service import list_low_stock_items
from .models import (
    Application,
    ApplicationStatus,
    Brand,
    Buyer,
    FranchiseOutlet,
    Inventory,
    SupplyRequest,
    SupplyRequestStatus,
)
from .schemas import AssistantQueryResponse, AssistantSuggestion

_log = logging.getLogger("franchisehub.agent.fo.tools")


def execute_fo_agent_tool(
    db: Session,
    owner_id: int,
    ctx: AgentOwnerContext,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    original_query: str,
) -> Optional[AssistantQueryResponse]:
    try:
        if tool_name == "get_low_stock":
            return _tool_low_stock(db, owner_id, arguments)
        if tool_name == "list_supply_requests":
            return _tool_supply_requests(db, owner_id, arguments)
        if tool_name == "list_pending_applications":
            return _tool_pending_applications(db, owner_id, arguments)
        if tool_name == "owner_dashboard_summary":
            return _tool_dashboard(db, owner_id)
        if tool_name == "list_my_outlets":
            return _tool_outlets(db, owner_id)
        if tool_name == "fo_general_help":
            return _tool_general_help(arguments)
    except Exception as exc:
        _log.warning("FO tool %s failed: %s", tool_name, exc)
    return None


def _owned_brand(db: Session, owner_id: int) -> Optional[Brand]:
    return db.scalar(
        select(Brand).where(Brand.franchise_owner_id == owner_id).order_by(Brand.id.asc())
    )


def _tool_low_stock(db: Session, owner_id: int, args: dict[str, Any]) -> AssistantQueryResponse:
    scope = args.get("scope") or "all"
    if scope == "all":
        scope = None
    limit = int(args.get("limit") or 10)
    items = list_low_stock_items(db, owner_id, scope=scope)[:limit]
    if not items:
        answer = "Düşük stoklu ürün bulunmuyor; tüm kalemler eşik üzerinde görünüyor."
    else:
        lines = []
        for item in items:
            loc = "merkez" if item.outlet_id is None else f"şube #{item.outlet_id}"
            lines.append(
                f"• {item.item_name}: {item.stock_level}/{item.low_stock_threshold} ({loc}, eksik {item.deficit})"
            )
        answer = f"{len(items)} düşük stok kalemi:\n" + "\n".join(lines)
    return AssistantQueryResponse(
        answer=answer,
        intent="low_stock",
        suggestions=[
            AssistantSuggestion(label="Şube stoğu", action="low_stock_outlet"),
            AssistantSuggestion(label="Tedarik talepleri", action="supply_requests"),
        ],
        filters_applied={"scope": args.get("scope") or "all", "count": len(items)},
        source="llm_tools",
    )


def _tool_supply_requests(
    db: Session, owner_id: int, args: dict[str, Any]
) -> AssistantQueryResponse:
    status_filter = str(args.get("status") or "pending")
    incoming_only = bool(args.get("incoming_only"))
    limit = int(args.get("limit") or 10)

    stmt = select(SupplyRequest).where(SupplyRequest.franchise_owner_id == owner_id)
    if incoming_only:
        stmt = stmt.where(SupplyRequest.outlet_id.isnot(None))
    if status_filter != "all":
        try:
            status_enum = SupplyRequestStatus(status_filter)
            stmt = stmt.where(SupplyRequest.status == status_enum)
        except ValueError:
            pass
    rows = db.scalars(
        stmt.order_by(SupplyRequest.created_at.desc(), SupplyRequest.id.desc()).limit(limit)
    ).all()

    if not rows:
        label = status_filter if status_filter != "all" else "kayıt"
        answer = f"{label} tedarik talebi bulunamadı."
    else:
        lines = []
        for row in rows:
            src = "şube" if row.outlet_id else "merkez"
            lines.append(
                f"• #{row.id} {row.product_name} x{row.quantity} — {row.status.value} ({src})"
            )
        answer = f"{len(rows)} tedarik talebi:\n" + "\n".join(lines)

    return AssistantQueryResponse(
        answer=answer,
        intent="supply_requests",
        filters_applied={"status": status_filter, "count": len(rows)},
        source="llm_tools",
    )


def _tool_pending_applications(
    db: Session, owner_id: int, args: dict[str, Any]
) -> AssistantQueryResponse:
    brand = _owned_brand(db, owner_id)
    if brand is None:
        return AssistantQueryResponse(
            answer="Henüz size atanmış bir marka yok; bekleyen başvuru listelenemiyor.",
            intent="pending_applications",
            source="llm_tools",
        )

    limit = int(args.get("limit") or 10)
    rows = db.scalars(
        select(Application)
        .where(
            Application.brand_id == brand.id,
            Application.status == ApplicationStatus.pending,
        )
        .order_by(Application.created_at.desc(), Application.id.desc())
        .limit(limit)
    ).all()

    if not rows:
        answer = f"{brand.name} için bekleyen başvuru yok."
    else:
        lines = []
        for app in rows:
            buyer = db.get(Buyer, app.buyer_id)
            name = f"{buyer.first_name} {buyer.last_name}" if buyer else f"Alıcı #{app.buyer_id}"
            lines.append(f"• #{app.id} {name} — {app.created_at.strftime('%d.%m.%Y')}")
        answer = f"{brand.name} — {len(rows)} bekleyen başvuru:\n" + "\n".join(lines)

    return AssistantQueryResponse(
        answer=answer,
        intent="pending_applications",
        filters_applied={"brand_id": brand.id, "count": len(rows)},
        source="llm_tools",
    )


def _tool_dashboard(db: Session, owner_id: int) -> AssistantQueryResponse:
    brand = _owned_brand(db, owner_id)
    inv_count = int(
        db.scalar(
            select(func.count(Inventory.id)).where(Inventory.franchise_owner_id == owner_id)
        )
        or 0
    )
    sr_pending = int(
        db.scalar(
            select(func.count(SupplyRequest.id)).where(
                SupplyRequest.franchise_owner_id == owner_id,
                SupplyRequest.status == SupplyRequestStatus.pending,
            )
        )
        or 0
    )
    sr_total = int(
        db.scalar(
            select(func.count(SupplyRequest.id)).where(
                SupplyRequest.franchise_owner_id == owner_id
            )
        )
        or 0
    )

    if brand is None:
        answer = (
            f"Panel özeti: {inv_count} envanter kalemi, "
            f"{sr_pending} bekleyen / {sr_total} toplam tedarik talebi. "
            "Atanmış marka yok."
        )
    else:
        pending = int(
            db.scalar(
                select(func.count(Application.id)).where(
                    Application.brand_id == brand.id,
                    Application.status == ApplicationStatus.pending,
                )
            )
            or 0
        )
        approved = int(
            db.scalar(
                select(func.count(Application.id)).where(
                    Application.brand_id == brand.id,
                    Application.status == ApplicationStatus.approved,
                )
            )
            or 0
        )
        answer = (
            f"{brand.name} panel özeti: {pending} bekleyen, {approved} onaylı başvuru; "
            f"{inv_count} envanter kalemi; {sr_pending} bekleyen / {sr_total} toplam tedarik."
        )

    return AssistantQueryResponse(
        answer=answer,
        intent="dashboard",
        filters_applied={
            "has_brand": brand is not None,
            "brand_id": brand.id if brand else None,
        },
        source="llm_tools",
    )


def _tool_outlets(db: Session, owner_id: int) -> AssistantQueryResponse:
    rows = db.scalars(
        select(FranchiseOutlet)
        .where(FranchiseOutlet.franchise_owner_id == owner_id)
        .order_by(FranchiseOutlet.id.asc())
    ).all()
    if not rows:
        answer = "Kayıtlı şube bulunmuyor."
    else:
        lines = [f"• #{o.id} {o.name} — {o.city}" for o in rows]
        answer = f"{len(rows)} şube:\n" + "\n".join(lines)
    return AssistantQueryResponse(
        answer=answer,
        intent="outlets",
        filters_applied={"count": len(rows)},
        source="llm_tools",
    )


def _tool_general_help(args: dict[str, Any]) -> AssistantQueryResponse:
    tone = str(args.get("tone") or "help")
    if tone == "greeting":
        answer = (
            "Merhaba! Düşük stok, tedarik talepleri, bekleyen başvurular veya panel özetini "
            "sorabilirsiniz. Örnek: «düşük stoklar neler» veya «kaç başvuru bekliyor»."
        )
    elif tone == "thanks":
        answer = "Rica ederim! Operasyon sorularınızda yardımcı olmaya devam ederim."
    else:
        answer = (
            "Franchise sahibi asistanı: stok, tedarik, başvuru ve şube bilgilerini "
            "panel verilerinden yanıtlarım."
        )
    return AssistantQueryResponse(
        answer=answer,
        intent="general",
        suggestions=[
            AssistantSuggestion(label="Düşük stok", action="low_stock"),
            AssistantSuggestion(label="Bekleyen başvurular", action="pending_applications"),
        ],
        source="llm_tools",
    )

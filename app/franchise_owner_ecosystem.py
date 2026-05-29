from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    Application,
    ApplicationStatus,
    Brand,
    Buyer,
    FranchiseOutlet,
    FranchiseOwnerDocument,
    Inventory,
    OutletStatus,
    SupplyRequest,
    SupplyRequestStatus,
)
from .schemas import (
    BrandRead,
    EcosystemEdge,
    EcosystemNode,
    FranchiseOwnerEcosystemResponse,
)


def build_franchise_owner_ecosystem(
    db: Session, franchise_owner_id: int
) -> FranchiseOwnerEcosystemResponse:
    brand = db.scalar(
        select(Brand).where(Brand.franchise_owner_id == franchise_owner_id)
    )
    brand_read = BrandRead.model_validate(brand) if brand else None

    outlets = []
    if brand:
        outlets = list(
            db.scalars(
                select(FranchiseOutlet).where(
                    FranchiseOutlet.franchise_owner_id == franchise_owner_id
                )
            ).all()
        )

    outlets_total = len(outlets)
    outlets_active = sum(1 for o in outlets if o.status == OutletStatus.active)

    documents_total = int(
        db.scalar(
            select(func.count(FranchiseOwnerDocument.id)).where(
                FranchiseOwnerDocument.franchise_owner_id == franchise_owner_id
            )
        )
        or 0
    )

    applications: list[Application] = []
    if brand:
        applications = list(
            db.scalars(
                select(Application).where(Application.brand_id == brand.id)
            ).all()
        )

    def _app_count(status: ApplicationStatus | None = None) -> int:
        if status is None:
            return len(applications)
        return sum(1 for a in applications if a.status == status)

    inventory_rows = db.scalars(
        select(Inventory).where(Inventory.franchise_owner_id == franchise_owner_id)
    ).all()
    inventory_item_count = len(inventory_rows)
    inventory_total_stock = sum(int(r.stock_level or 0) for r in inventory_rows)

    supply_pending = int(
        db.scalar(
            select(func.count(SupplyRequest.id)).where(
                SupplyRequest.franchise_owner_id == franchise_owner_id,
                SupplyRequest.status == SupplyRequestStatus.pending,
            )
        )
        or 0
    )
    supply_total = int(
        db.scalar(
            select(func.count(SupplyRequest.id)).where(
                SupplyRequest.franchise_owner_id == franchise_owner_id
            )
        )
        or 0
    )

    nodes: list[EcosystemNode] = []
    edges: list[EcosystemEdge] = []

    if brand:
        brand_node_id = f"brand-{brand.id}"
        nodes.append(
            EcosystemNode(
                id=brand_node_id,
                type="brand",
                label=brand.name,
                meta={"brand_id": brand.id, "is_approved": brand.is_approved},
            )
        )
        for outlet in outlets:
            node_id = f"outlet-{outlet.id}"
            nodes.append(
                EcosystemNode(
                    id=node_id,
                    type="outlet",
                    label=outlet.name,
                    meta={
                        "outlet_id": outlet.id,
                        "city": outlet.city,
                        "status": outlet.status.value,
                    },
                )
            )
            edges.append(
                EcosystemEdge(
                    id=f"edge-brand-outlet-{outlet.id}",
                    source=brand_node_id,
                    target=node_id,
                    type="operates",
                )
            )

        for app in applications[:25]:
            buyer = db.get(Buyer, app.buyer_id)
            buyer_label = (
                f"{buyer.first_name} {buyer.last_name}".strip() if buyer else f"Buyer #{app.buyer_id}"
            )
            node_id = f"application-{app.id}"
            nodes.append(
                EcosystemNode(
                    id=node_id,
                    type="application",
                    label=buyer_label,
                    meta={
                        "application_id": app.id,
                        "status": app.status.value,
                        "buyer_id": app.buyer_id,
                    },
                )
            )
            edges.append(
                EcosystemEdge(
                    id=f"edge-brand-app-{app.id}",
                    source=brand_node_id,
                    target=node_id,
                    type="application",
                )
            )

    return FranchiseOwnerEcosystemResponse(
        has_brand=brand is not None,
        brand=brand_read,
        outlets_total=outlets_total,
        outlets_active=outlets_active,
        documents_total=documents_total,
        applications_pending=_app_count(ApplicationStatus.pending),
        applications_approved=_app_count(ApplicationStatus.approved),
        applications_rejected=_app_count(ApplicationStatus.rejected),
        applications_total=_app_count(),
        inventory_item_count=inventory_item_count,
        inventory_total_stock=inventory_total_stock,
        supply_requests_pending=supply_pending,
        supply_requests_total=supply_total,
        nodes=nodes,
        edges=edges,
    )

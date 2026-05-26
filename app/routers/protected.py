from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_principal, require_roles
from ..models import (
    Application,
    Inventory,
    SupplyRequest,
    SupplyRequestStatus,
    UserRole,
)
from ..schemas import (
    ApplicationRead,
    AuthenticatedPrincipal,
    InventoryItemCreate,
    InventoryItemUpdate,
    InventoryListEnvelope,
    InventoryRead,
    SupplyPoolItem,
    SupplyRequestBulkCreate,
    SupplyRequestListEnvelope,
    SupplyRequestRead,
)

router = APIRouter(tags=["protected"])


@router.get(
    "/inventory",
    response_model=InventoryListEnvelope,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def list_my_inventory(
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    result = db.scalars(
        select(Inventory).where(Inventory.franchise_owner_id == current_user.user_id)
    ).all()
    return InventoryListEnvelope(items=result)


@router.post(
    "/inventory",
    response_model=InventoryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def create_inventory_item(
    payload: InventoryItemCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    item = Inventory(
        franchise_owner_id=current_user.user_id,
        item_name=payload.item_name,
        stock_level=payload.stock_level,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch(
    "/inventory/{inventory_id}",
    response_model=InventoryRead,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def update_inventory_item(
    inventory_id: int,
    payload: InventoryItemUpdate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    item = db.get(Inventory, inventory_id)
    if not item or item.franchise_owner_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )

    if payload.item_name is not None:
        item.item_name = payload.item_name
    if payload.stock_level is not None:
        item.stock_level = payload.stock_level

    db.commit()
    db.refresh(item)
    return item


@router.delete(
    "/inventory/{inventory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def delete_inventory_item(
    inventory_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    item = db.get(Inventory, inventory_id)
    if not item or item.franchise_owner_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )
    db.delete(item)
    db.commit()


@router.get(
    "/supply-requests",
    response_model=SupplyRequestListEnvelope,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def list_my_supply_requests(
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    rows = db.scalars(
        select(SupplyRequest)
        .where(SupplyRequest.franchise_owner_id == current_user.user_id)
        .order_by(SupplyRequest.id.desc())
    ).all()
    return SupplyRequestListEnvelope(items=rows)


@router.post(
    "/supply-requests/bulk",
    response_model=list[SupplyRequestRead],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def create_bulk_supply_requests(
    payload: SupplyRequestBulkCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    created_requests: list[SupplyRequest] = []
    for req in payload.requests:
        supply_request = SupplyRequest(
            franchise_owner_id=current_user.user_id,
            product_name=req.product_name,
            quantity=req.quantity,
            status=SupplyRequestStatus.pending,
        )
        db.add(supply_request)
        created_requests.append(supply_request)

    db.commit()
    for request_item in created_requests:
        db.refresh(request_item)
    return created_requests


@router.get(
    "/supply-requests/pool",
    response_model=list[SupplyPoolItem],
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def get_supply_pool(
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    # Pool only includes other franchise owners to discover collective demand.
    rows = db.execute(
        select(
            SupplyRequest.product_name,
            func.sum(SupplyRequest.quantity).label("total_quantity"),
            func.count(SupplyRequest.id).label("request_count"),
            func.count(func.distinct(SupplyRequest.franchise_owner_id)).label(
                "franchise_owner_count"
            ),
        )
        .where(
            SupplyRequest.status == SupplyRequestStatus.pending,
            SupplyRequest.franchise_owner_id != current_user.user_id,
        )
        .group_by(SupplyRequest.product_name)
        .order_by(func.sum(SupplyRequest.quantity).desc())
    ).all()

    return [
        SupplyPoolItem(
            product_name=row.product_name,
            total_quantity=int(row.total_quantity or 0),
            request_count=int(row.request_count or 0),
            franchise_owner_count=int(row.franchise_owner_count or 0),
        )
        for row in rows
    ]


@router.get(
    "/applications",
    response_model=list[ApplicationRead],
    dependencies=[Depends(require_roles(UserRole.franchise_owner, UserRole.admin))],
)
def list_applications(db: Session = Depends(get_db)):
    return db.scalars(select(Application)).all()

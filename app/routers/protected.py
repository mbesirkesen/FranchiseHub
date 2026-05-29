from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_principal, require_roles
from ..inventory_service import list_low_stock_items, transfer_between_outlets
from ..models import (
    Inventory,
    SupplyRequest,
    SupplyRequestStatus,
    UserRole,
)
from ..schemas import (
    AuthenticatedPrincipal,
    InventoryItemCreate,
    InventoryItemUpdate,
    InventoryListEnvelope,
    InventoryRead,
    InventoryTransferRead,
    InventoryTransferRequest,
    LowStockListResponse,
    SupplyPoolItem,
    SupplyRequestBulkCreate,
    SupplyRequestDetailRead,
    SupplyRequestListEnvelope,
    SupplyRequestRead,
    SupplyRequestUpdate,
)
from ..pagination import paginated_meta
from ..supply_service import get_supply_request_for_owner, update_supply_request_status

router = APIRouter(tags=["protected"])


@router.get(
    "/inventory",
    response_model=InventoryListEnvelope,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def list_my_inventory(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    stmt = (
        select(Inventory)
        .where(Inventory.franchise_owner_id == current_user.user_id)
        .order_by(Inventory.id.desc())
    )
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    offset = (page - 1) * page_size
    result = db.scalars(stmt.offset(offset).limit(page_size)).all()
    meta = paginated_meta(total, page, page_size)
    return InventoryListEnvelope(items=list(result), **meta)


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
        outlet_id=payload.outlet_id,
        item_name=payload.item_name,
        stock_level=payload.stock_level,
        low_stock_threshold=payload.low_stock_threshold,
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
    if payload.outlet_id is not None:
        item.outlet_id = payload.outlet_id
    if payload.low_stock_threshold is not None:
        item.low_stock_threshold = payload.low_stock_threshold

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


@router.post(
    "/inventory/transfer",
    response_model=InventoryTransferRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def transfer_inventory(
    payload: InventoryTransferRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    transfer, source, dest = transfer_between_outlets(
        db,
        current_user,
        inventory_id=payload.inventory_id,
        from_outlet_id=payload.from_outlet_id,
        to_outlet_id=payload.to_outlet_id,
        quantity=payload.quantity,
    )
    return InventoryTransferRead(
        id=transfer.id,
        franchise_owner_id=transfer.franchise_owner_id,
        from_outlet_id=transfer.from_outlet_id,
        to_outlet_id=transfer.to_outlet_id,
        inventory_id=transfer.inventory_id,
        item_name=transfer.item_name,
        quantity=transfer.quantity,
        created_at=transfer.created_at,
        source_stock_after=source.stock_level,
        destination_stock_after=dest.stock_level,
    )


@router.get(
    "/inventory/low-stock",
    response_model=LowStockListResponse,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def list_low_stock(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    all_items = list_low_stock_items(db, current_user.user_id)
    total = len(all_items)
    start = (page - 1) * page_size
    items = all_items[start : start + page_size]
    meta = paginated_meta(total, page, page_size)
    return LowStockListResponse(items=items, **meta)


@router.get(
    "/supply-requests",
    response_model=SupplyRequestListEnvelope,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def list_my_supply_requests(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    stmt = (
        select(SupplyRequest)
        .where(SupplyRequest.franchise_owner_id == current_user.user_id)
        .order_by(SupplyRequest.created_at.desc(), SupplyRequest.id.desc())
    )
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    offset = (page - 1) * page_size
    rows = db.scalars(stmt.offset(offset).limit(page_size)).all()
    meta = paginated_meta(total, page, page_size)
    return SupplyRequestListEnvelope(items=list(rows), **meta)


@router.get(
    "/supply-requests/{request_id}",
    response_model=SupplyRequestDetailRead,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def get_supply_request_detail(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    item = get_supply_request_for_owner(db, request_id, current_user.user_id)
    return item


@router.patch(
    "/supply-requests/{request_id}",
    response_model=SupplyRequestDetailRead,
    dependencies=[Depends(require_roles(UserRole.franchise_owner))],
)
def patch_supply_request(
    request_id: int,
    payload: SupplyRequestUpdate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedPrincipal = Depends(get_current_principal),
):
    item = get_supply_request_for_owner(db, request_id, current_user.user_id)
    return update_supply_request_status(
        db, item, new_status=payload.status, notes=payload.notes
    )


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

    now = datetime.utcnow()
    for request_item in created_requests:
        request_item.updated_at = now
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


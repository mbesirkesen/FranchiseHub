from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Application, ApplicationStatus, Brand, Inventory, SupplyRequest, SupplyRequestStatus
from .schemas import (
    AnalyticsMonthPoint,
    AnalyticsTimePoint,
    FranchiseOwnerAnalyticsResponse,
    InventoryTimePoint,
    SupplyRequestsByStatus,
)
from .security import utc_now


def _date_key(dt: datetime) -> str:
    return dt.date().isoformat()


def _fill_date_range(days: int) -> list[date]:
    end = utc_now().date()
    start = end - timedelta(days=days - 1)
    out: list[date] = []
    current = start
    while current <= end:
        out.append(current)
        current += timedelta(days=1)
    return out


def build_owner_analytics(
    db: Session,
    *,
    franchise_owner_id: int,
    brand_id: Optional[int],
    days: int = 30,
) -> FranchiseOwnerAnalyticsResponse:
    days = max(1, min(days, 365))
    day_keys = [d.isoformat() for d in _fill_date_range(days)]

    app_buckets: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "pending": 0, "approved": 0, "rejected": 0}
    )
    if brand_id is not None:
        since = utc_now() - timedelta(days=days)
        apps = db.scalars(
            select(Application).where(
                Application.brand_id == brand_id,
                Application.created_at >= since,
            )
        ).all()
        for app in apps:
            if not app.created_at:
                continue
            key = _date_key(app.created_at)
            app_buckets[key]["total"] += 1
            status_key = app.status.value
            if status_key in app_buckets[key]:
                app_buckets[key][status_key] += 1

    application_points = [
        AnalyticsTimePoint(
            date=key,
            total=app_buckets[key]["total"],
            pending=app_buckets[key]["pending"],
            approved=app_buckets[key]["approved"],
            rejected=app_buckets[key]["rejected"],
        )
        for key in day_keys
    ]
    applications_total_in_period = sum(p.total for p in application_points)

    month_buckets: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "pending": 0, "approved": 0, "rejected": 0}
    )
    if brand_id is not None:
        since = utc_now() - timedelta(days=days)
        for app in db.scalars(
            select(Application).where(
                Application.brand_id == brand_id,
                Application.created_at >= since,
            )
        ).all():
            if not app.created_at:
                continue
            month_key = app.created_at.strftime("%Y-%m")
            month_buckets[month_key]["total"] += 1
            sk = app.status.value
            if sk in month_buckets[month_key]:
                month_buckets[month_key][sk] += 1
    applications_by_month = [
        AnalyticsMonthPoint(month=m, **month_buckets[m])
        for m in sorted(month_buckets.keys())
    ]

    supply_requests_total = int(
        db.scalar(
            select(func.count(SupplyRequest.id)).where(
                SupplyRequest.franchise_owner_id == franchise_owner_id
            )
        )
        or 0
    )

    inv_rows = db.scalars(
        select(Inventory).where(Inventory.franchise_owner_id == franchise_owner_id)
    ).all()
    item_count = len(inv_rows)
    total_stock = sum(int(r.stock_level or 0) for r in inv_rows)

    since = utc_now() - timedelta(days=days)
    supply_rows = db.scalars(
        select(SupplyRequest).where(
            SupplyRequest.franchise_owner_id == franchise_owner_id,
            SupplyRequest.created_at >= since,
        )
    ).all()
    supply_by_day: dict[str, int] = defaultdict(int)
    for row in supply_rows:
        if row.created_at:
            supply_by_day[_date_key(row.created_at)] += 1
    supply_requests_in_period = len(supply_rows)

    supply_status_counts = SupplyRequestsByStatus(
        pending=int(
            db.scalar(
                select(func.count(SupplyRequest.id)).where(
                    SupplyRequest.franchise_owner_id == franchise_owner_id,
                    SupplyRequest.status == SupplyRequestStatus.pending,
                )
            )
            or 0
        ),
        approved=int(
            db.scalar(
                select(func.count(SupplyRequest.id)).where(
                    SupplyRequest.franchise_owner_id == franchise_owner_id,
                    SupplyRequest.status == SupplyRequestStatus.approved,
                )
            )
            or 0
        ),
        rejected=int(
            db.scalar(
                select(func.count(SupplyRequest.id)).where(
                    SupplyRequest.franchise_owner_id == franchise_owner_id,
                    SupplyRequest.status == SupplyRequestStatus.rejected,
                )
            )
            or 0
        ),
        shipped=int(
            db.scalar(
                select(func.count(SupplyRequest.id)).where(
                    SupplyRequest.franchise_owner_id == franchise_owner_id,
                    SupplyRequest.status == SupplyRequestStatus.shipped,
                )
            )
            or 0
        ),
    )

    inventory_points = [
        InventoryTimePoint(
            date=key,
            item_count=item_count,
            total_stock=total_stock,
            supply_request_count=supply_by_day.get(key, 0),
        )
        for key in day_keys
    ]

    return FranchiseOwnerAnalyticsResponse(
        period_days=days,
        applications=application_points,
        inventory=inventory_points,
        applications_total_in_period=applications_total_in_period,
        supply_requests_total=supply_requests_total,
        supply_requests_total_in_period=supply_requests_in_period,
        inventory_current={
            "item_count": item_count,
            "total_stock": total_stock,
        },
        applications_by_month=applications_by_month,
        inventory_total_quantity=total_stock,
        supply_requests_by_status=supply_status_counts,
    )

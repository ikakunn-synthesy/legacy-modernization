from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AllocationRecord, OrderDetail, WarehouseInventory


def allocate_detail(session: Session, detail: OrderDetail) -> list[AllocationRecord]:
    already_allocated = session.scalar(select(func.coalesce(func.sum(AllocationRecord.allocated_quantity), 0)).where(AllocationRecord.order_detail_id == detail.id, AllocationRecord.action == "allocated"))
    returned = session.scalar(select(func.coalesce(func.sum(AllocationRecord.allocated_quantity), 0)).where(AllocationRecord.order_detail_id == detail.id, AllocationRecord.action == "returned"))
    remaining = detail.quantity - Decimal(already_allocated or 0) + Decimal(returned or 0)
    if remaining <= 0:
        return []
    inventory = list(session.scalars(select(WarehouseInventory).where(WarehouseInventory.item_id == detail.item_id, WarehouseInventory.available_quantity > 0)))
    inventory.sort(key=lambda row: (row.warehouse != detail.warehouse, -row.available_quantity, row.warehouse))
    records = []
    allocated_total = Decimal("0")
    for row in inventory:
        if remaining <= 0:
            break
        allocated = min(row.available_quantity, remaining)
        row.available_quantity -= allocated
        remaining -= allocated
        allocated_total += allocated
        record = AllocationRecord(order_detail_id=detail.id, warehouse=row.warehouse, allocated_quantity=allocated, shortage_quantity=Decimal("0"), state="allocated", action="allocated")
        session.add(record)
        records.append(record)
    if remaining > 0:
        record = AllocationRecord(order_detail_id=detail.id, warehouse=detail.warehouse, allocated_quantity=Decimal("0"), shortage_quantity=remaining, state="awaiting_arrival", action="shortage_recorded")
        session.add(record)
        records.append(record)
    detail.state = "allocated" if remaining == 0 else "partially_allocated_awaiting_arrival" if allocated_total else "awaiting_arrival"
    return records


def reallocate_awaiting_details(session: Session) -> list[str]:
    details = list(session.scalars(select(OrderDetail).where(OrderDetail.state.in_(["awaiting_arrival", "partially_allocated_awaiting_arrival"])).order_by(OrderDetail.delivery_date, OrderDetail.id)))
    changed = []
    for detail in details:
        if allocate_detail(session, detail):
            changed.append(detail.id)
    return changed


def cancel_allocations(session: Session, detail: OrderDetail) -> list[AllocationRecord]:
    active = list(session.scalars(select(AllocationRecord).where(AllocationRecord.order_detail_id == detail.id, AllocationRecord.action == "allocated")))
    returned_total = session.scalar(select(func.coalesce(func.sum(AllocationRecord.allocated_quantity), 0)).where(AllocationRecord.order_detail_id == detail.id, AllocationRecord.action == "returned"))
    remaining_to_return = sum((allocation.allocated_quantity for allocation in active), Decimal("0")) - Decimal(returned_total or 0)
    returns = []
    for allocation in active:
        if remaining_to_return <= 0:
            break
        quantity = min(allocation.allocated_quantity, remaining_to_return)
        balance = session.scalar(select(WarehouseInventory).where(WarehouseInventory.warehouse == allocation.warehouse, WarehouseInventory.item_id == detail.item_id))
        if balance:
            balance.available_quantity += quantity
        returned = AllocationRecord(order_detail_id=detail.id, warehouse=allocation.warehouse, allocated_quantity=quantity, shortage_quantity=Decimal("0"), state="cancelled", action="returned")
        session.add(returned)
        returns.append(returned)
        remaining_to_return -= quantity
    detail.state = "cancelled"
    return returns

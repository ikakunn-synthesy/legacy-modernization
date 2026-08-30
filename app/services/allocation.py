from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AllocationRecord, OrderDetail, WarehouseInventory


def allocate_detail(session: Session, detail: OrderDetail) -> list[AllocationRecord]:
    already_allocated = session.scalar(select(func.coalesce(func.sum(AllocationRecord.allocated_quantity), 0)).where(AllocationRecord.order_detail_id == detail.id, AllocationRecord.action == "allocated"))
    remaining = detail.quantity - Decimal(already_allocated or 0)
    if remaining <= 0:
        return []
    inventory = list(session.scalars(select(WarehouseInventory).where(WarehouseInventory.item_id == detail.item_id, WarehouseInventory.available_quantity > 0)))
    inventory.sort(key=lambda row: (row.warehouse != detail.warehouse, -row.available_quantity, row.warehouse))
    records = []
    for row in inventory:
        if remaining <= 0:
            break
        allocated = min(row.available_quantity, remaining)
        row.available_quantity -= allocated
        remaining -= allocated
        record = AllocationRecord(order_detail_id=detail.id, warehouse=row.warehouse, allocated_quantity=allocated, shortage_quantity=Decimal("0"), state="allocated", action="allocated")
        session.add(record)
        records.append(record)
    if remaining > 0:
        record = AllocationRecord(order_detail_id=detail.id, warehouse=detail.warehouse, allocated_quantity=Decimal("0"), shortage_quantity=remaining, state="awaiting_arrival", action="shortage_recorded")
        session.add(record)
        records.append(record)
    detail.state = "allocated" if remaining == 0 else "partially_allocated_awaiting_arrival" if records[:-1] else "awaiting_arrival"
    return records


def cancel_allocations(session: Session, detail: OrderDetail) -> list[AllocationRecord]:
    active = list(session.scalars(select(AllocationRecord).where(AllocationRecord.order_detail_id == detail.id, AllocationRecord.action == "allocated")))
    returns = []
    for allocation in active:
        balance = session.scalar(select(WarehouseInventory).where(WarehouseInventory.warehouse == allocation.warehouse, WarehouseInventory.item_id == detail.item_id))
        if balance:
            balance.available_quantity += allocation.allocated_quantity
        returned = AllocationRecord(order_detail_id=detail.id, warehouse=allocation.warehouse, allocated_quantity=allocation.allocated_quantity, shortage_quantity=Decimal("0"), state="cancelled", action="returned")
        session.add(returned)
        returns.append(returned)
    detail.state = "cancelled"
    return returns

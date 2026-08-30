from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AllocationRecord, InventoryClassificationConversion, InventoryClassificationReview, InventoryLedgerEntry, OrderDetail, WarehouseInventory


SOURCE_CLASSIFICATION = "finished_goods"


def _record_ledger_entry(session: Session, detail: OrderDetail, warehouse: str, quantity: Decimal, action: str, balance: Decimal) -> bool:
    source_transaction = f"allocation:{detail.id}:{warehouse}:{action}"
    mapping = session.scalar(select(InventoryClassificationConversion).where(InventoryClassificationConversion.source_system == "sales", InventoryClassificationConversion.source_classification == SOURCE_CLASSIFICATION))
    if mapping is None:
        session.add(InventoryClassificationReview(source_system="sales", source_transaction=source_transaction, source_classification=SOURCE_CLASSIFICATION, requested_common_classification="finished_goods", reason="No approved inventory classification mapping exists"))
        return False
    session.add(InventoryLedgerEntry(source_system="sales", source_transaction=source_transaction, source_classification=SOURCE_CLASSIFICATION, quantity=quantity, quantity_precision=3, common_classification=mapping.common_classification, resulting_balance=balance))
    return True


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
        if not _record_ledger_entry(session, detail, row.warehouse, -allocated, "allocate", row.available_quantity - allocated):
            detail.state = "inventory_classification_review"
            return records
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
    return [detail.id for detail in details if allocate_detail(session, detail)]


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
        if balance is None or not _record_ledger_entry(session, detail, allocation.warehouse, quantity, "return", balance.available_quantity + quantity):
            continue
        balance.available_quantity += quantity
        returned = AllocationRecord(order_detail_id=detail.id, warehouse=allocation.warehouse, allocated_quantity=quantity, shortage_quantity=Decimal("0"), state="cancelled", action="returned")
        session.add(returned)
        returns.append(returned)
        remaining_to_return -= quantity
    detail.state = "cancelled"
    return returns

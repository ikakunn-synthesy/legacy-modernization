from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AllocationRecord, OrderDetail
from app.shipment_models import ShipmentDetail


def available_to_ship(session: Session, detail: OrderDetail, warehouse: str) -> Decimal:
    allocated = session.scalar(select(func.coalesce(func.sum(AllocationRecord.allocated_quantity), 0)).where(AllocationRecord.order_detail_id == detail.id, AllocationRecord.warehouse == warehouse, AllocationRecord.action == "allocated"))
    returned = session.scalar(select(func.coalesce(func.sum(AllocationRecord.allocated_quantity), 0)).where(AllocationRecord.order_detail_id == detail.id, AllocationRecord.warehouse == warehouse, AllocationRecord.action == "returned"))
    shipped = session.scalar(select(func.coalesce(func.sum(ShipmentDetail.shipped_quantity), 0)).where(ShipmentDetail.order_detail_id == detail.id, ShipmentDetail.warehouse == warehouse, ShipmentDetail.sales_posting_state != "cancelled"))
    return Decimal(allocated or 0) - Decimal(returned or 0) - Decimal(shipped or 0)

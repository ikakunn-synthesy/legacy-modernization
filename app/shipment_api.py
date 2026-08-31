from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Order, OrderDetail, WarehouseInventory
from app.schemas import ShipmentCancellationCreate, ShipmentConfirmationCreate, ShipmentCreate
from app.shipment_models import Shipment, ShipmentConfirmation, ShipmentDetail
from app.services.inventory_ledger import record_inventory_update
from app.services.shipping import available_to_ship

router = APIRouter()


@router.post("/shipments", status_code=status.HTTP_201_CREATED)
def create_shipment(payload: ShipmentCreate, session: Session = Depends(get_session)) -> dict[str, object]:
    order = session.get(Order, payload.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    prepared = []
    for line in payload.details:
        detail = session.get(OrderDetail, line.order_detail_id)
        if detail is None or detail.order_id != order.id or detail.unit_price is None:
            raise HTTPException(status_code=422, detail="Shipment detail must belong to the order and have a fixed price")
        if line.shipped_quantity > available_to_ship(session, detail, line.warehouse):
            raise HTTPException(status_code=422, detail="Shipment quantity exceeds allocated and unshipped quantity")
        prepared.append((line, detail))
    shipment_number = (session.scalar(select(func.max(Shipment.shipment_number))) or 0) + 1
    shipment = Shipment(shipment_number=shipment_number, order_id=order.id, shipment_date=payload.shipment_date)
    session.add(shipment)
    session.flush()
    details = []
    for line, detail in prepared:
        shipment_detail = ShipmentDetail(shipment_id=shipment.id, order_detail_id=detail.id, warehouse=line.warehouse, shipped_quantity=line.shipped_quantity, unit_price=detail.unit_price, amount=line.shipped_quantity * detail.unit_price)
        session.add(shipment_detail)
        details.append(shipment_detail)
    session.commit()
    return {"shipment_number": shipment.shipment_number, "state": shipment.state, "details": [{"id": detail.id, "amount": str(detail.amount), "sales_posting_state": detail.sales_posting_state} for detail in details]}


@router.post("/shipment-details/{shipment_detail_id}/confirm")
def confirm_shipment_amount(shipment_detail_id: str, payload: ShipmentConfirmationCreate, session: Session = Depends(get_session)) -> dict[str, str]:
    detail = session.get(ShipmentDetail, shipment_detail_id)
    if detail is None or detail.sales_posting_state == "cancelled":
        raise HTTPException(status_code=404, detail="Active shipment detail not found")
    detail.sales_posting_state = "eligible"
    session.add(ShipmentConfirmation(shipment_detail_id=detail.id, confirmed_by=payload.confirmed_by, action="confirmed"))
    session.commit()
    return {"id": detail.id, "sales_posting_state": detail.sales_posting_state}


@router.post("/shipment-details/{shipment_detail_id}/cancel")
def cancel_shipment(shipment_detail_id: str, payload: ShipmentCancellationCreate, session: Session = Depends(get_session)) -> dict[str, str]:
    shipment_detail = session.get(ShipmentDetail, shipment_detail_id)
    if shipment_detail is None or shipment_detail.sales_posting_state in {"eligible", "cancelled"}:
        raise HTTPException(status_code=422, detail="Only unposted shipment details can be cancelled")
    order_detail = session.get(OrderDetail, shipment_detail.order_detail_id)
    balance = session.scalar(select(WarehouseInventory).where(WarehouseInventory.warehouse == shipment_detail.warehouse, WarehouseInventory.item_id == order_detail.item_id))
    current = balance.available_quantity if balance else Decimal("0")
    resulting_balance = current + shipment_detail.shipped_quantity
    if not record_inventory_update(session, source_system="sales", source_transaction=f"shipment:{shipment_detail.id}:cancel", source_classification="finished_goods", quantity=shipment_detail.shipped_quantity, resulting_balance=resulting_balance):
        session.commit()
        raise HTTPException(status_code=202, detail="Shipment cancellation requires classification review")
    if balance is None:
        balance = WarehouseInventory(warehouse=shipment_detail.warehouse, item_id=order_detail.item_id, available_quantity=resulting_balance)
        session.add(balance)
    else:
        balance.available_quantity = resulting_balance
    shipment_detail.sales_posting_state = "cancelled"
    shipment_detail.cancelled_at = datetime.now(timezone.utc)
    session.add(ShipmentConfirmation(shipment_detail_id=shipment_detail.id, confirmed_by=payload.cancelled_by, action="cancelled"))
    session.commit()
    return {"id": shipment_detail.id, "sales_posting_state": shipment_detail.sales_posting_state}

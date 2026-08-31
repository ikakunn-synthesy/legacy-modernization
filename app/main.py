from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import Base, engine, get_session
from app.models import Customer, InventoryClassificationConversion, Item, Order, OrderDetail, PriceAgreement, WarehouseInventory
from app.schemas import AllocationCancellationRequest, AllocationRequest, CustomerCreate, InventoryBalanceUpdate, InventoryMappingCreate, ItemCreate, OrderCreate, PriceAgreementCreate
from app.services.allocation import allocate_detail, cancel_allocations, reallocate_awaiting_details
from app.services.inventory_ledger import record_inventory_update
from app.services.pricing import resolve_price
from app.shipment_api import router as shipment_router
from app import shipment_models  # Register shipment tables with SQLAlchemy metadata.

app = FastAPI(title="Legacy Modernization API", version="0.5.0")
app.include_router(shipment_router)


@app.on_event("startup")
def create_schema() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/customers", status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, session: Session = Depends(get_session)) -> dict[str, str]:
    customer = Customer(**payload.model_dump())
    session.add(customer)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Customer already exists") from exc
    return {"id": customer.id}


@app.post("/items", status_code=status.HTTP_201_CREATED)
def create_item(payload: ItemCreate, session: Session = Depends(get_session)) -> dict[str, str]:
    item = Item(**payload.model_dump())
    session.add(item)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Item already exists") from exc
    return {"id": item.id}


@app.post("/price-agreements", status_code=status.HTTP_201_CREATED)
def create_price_agreement(payload: PriceAgreementCreate, session: Session = Depends(get_session)) -> dict[str, str | int]:
    if session.get(Customer, payload.customer_id) is None or session.get(Item, payload.item_id) is None:
        raise HTTPException(status_code=422, detail="Customer and item must exist before a price agreement is created")
    latest_version = session.scalar(select(func.max(PriceAgreement.version)).where(PriceAgreement.customer_id == payload.customer_id, PriceAgreement.item_id == payload.item_id))
    agreement = PriceAgreement(**payload.model_dump(), version=(latest_version or 0) + 1)
    session.add(agreement)
    session.commit()
    return {"id": agreement.id, "version": agreement.version}


@app.post("/inventory-classification-mappings", status_code=status.HTTP_201_CREATED)
def create_inventory_mapping(payload: InventoryMappingCreate, session: Session = Depends(get_session)) -> dict[str, str]:
    mapping = InventoryClassificationConversion(**payload.model_dump())
    session.add(mapping)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="A mapping already exists for this source classification") from exc
    return {"id": mapping.id}


@app.post("/orders", status_code=status.HTTP_201_CREATED)
def create_order(payload: OrderCreate, session: Session = Depends(get_session)) -> dict[str, object]:
    if session.get(Customer, payload.customer_id) is None:
        raise HTTPException(status_code=422, detail="Customer does not exist")
    if payload.delivery_date < payload.order_date or any(detail.delivery_date < payload.order_date for detail in payload.details):
        raise HTTPException(status_code=422, detail="Delivery date cannot precede order date")
    if any(session.get(Item, detail.item_id) is None for detail in payload.details):
        raise HTTPException(status_code=422, detail="Each order item must exist")
    resolved_details = []
    hold = False
    for detail in payload.details:
        resolved = resolve_price(session, payload.customer_id, detail.item_id, detail.quantity, payload.order_date)
        if detail.manual_price is not None:
            if resolved.price != detail.manual_price and not detail.manual_difference_reason:
                raise HTTPException(status_code=422, detail="Manual price requires a difference reason")
            price, basis, version = detail.manual_price, "manual", resolved.agreement_version
        else:
            price, basis, version = resolved.price, resolved.basis_type, resolved.agreement_version
        hold = hold or price is None
        resolved_details.append((detail, price, basis, version))
    next_number = (session.scalar(select(func.max(Order.order_number))) or 0) + 1
    order = Order(order_number=next_number, customer_id=payload.customer_id, order_date=payload.order_date, delivery_date=payload.delivery_date, channel=payload.channel, state="price_unset_hold" if hold else "ready", total_amount=Decimal("0"))
    session.add(order)
    session.flush()
    total = Decimal("0")
    for line_number, (detail, price, basis, version) in enumerate(resolved_details, start=1):
        amount = price * detail.quantity if price is not None else None
        total += amount or Decimal("0")
        session.add(OrderDetail(order_id=order.id, line_number=line_number, item_id=detail.item_id, quantity=detail.quantity, unit_price=price, amount=amount, delivery_date=detail.delivery_date, warehouse=detail.warehouse, state="price_unset_hold" if price is None else "ready", price_basis_type=basis, price_agreement_version=version, manual_difference_reason=detail.manual_difference_reason))
    order.total_amount = total
    session.commit()
    return {"id": order.id, "order_number": order.order_number, "state": order.state, "total_amount": str(order.total_amount)}


@app.get("/orders/{order_number}")
def get_order(order_number: int, session: Session = Depends(get_session)) -> dict[str, object]:
    order = session.scalar(select(Order).where(Order.order_number == order_number))
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    details = list(session.scalars(select(OrderDetail).where(OrderDetail.order_id == order.id).order_by(OrderDetail.line_number)))
    return {"order_number": order.order_number, "state": order.state, "total_amount": str(order.total_amount), "details": [{"line_number": detail.line_number, "item_id": detail.item_id, "quantity": str(detail.quantity), "unit_price": str(detail.unit_price) if detail.unit_price is not None else None, "amount": str(detail.amount) if detail.amount is not None else None, "state": detail.state, "price_basis_type": detail.price_basis_type, "price_agreement_version": detail.price_agreement_version, "manual_difference_reason": detail.manual_difference_reason} for detail in details]}


@app.post("/inventory/balances")
def update_inventory_balance(payload: InventoryBalanceUpdate, session: Session = Depends(get_session)) -> dict[str, object]:
    if session.get(Item, payload.item_id) is None:
        raise HTTPException(status_code=422, detail="Item does not exist")
    balance = session.scalar(select(WarehouseInventory).where(WarehouseInventory.warehouse == payload.warehouse, WarehouseInventory.item_id == payload.item_id))
    current = balance.available_quantity if balance else Decimal("0")
    resulting_balance = current + payload.quantity_change
    if resulting_balance < 0:
        raise HTTPException(status_code=422, detail="Inventory cannot become negative")
    if not record_inventory_update(session, source_system=payload.source_system, source_transaction=payload.source_transaction, source_classification=payload.source_classification, quantity=payload.quantity_change, resulting_balance=resulting_balance):
        session.commit()
        raise HTTPException(status_code=202, detail="Inventory update requires classification review")
    if balance is None:
        session.add(WarehouseInventory(warehouse=payload.warehouse, item_id=payload.item_id, available_quantity=resulting_balance))
    else:
        balance.available_quantity = resulting_balance
    reallocated = reallocate_awaiting_details(session) if payload.quantity_change > 0 else []
    session.commit()
    return {"warehouse": payload.warehouse, "item_id": payload.item_id, "available_quantity": str(resulting_balance), "reallocated_detail_ids": reallocated}


@app.post("/allocations")
def allocate_order_detail(payload: AllocationRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    detail = session.get(OrderDetail, payload.order_detail_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Order detail not found")
    if detail.state not in {"ready", "awaiting_arrival", "partially_allocated_awaiting_arrival"}:
        raise HTTPException(status_code=422, detail="Order detail is not eligible for allocation")
    records = allocate_detail(session, detail)
    session.commit()
    return {"detail_state": detail.state, "records": [{"warehouse": record.warehouse, "allocated_quantity": str(record.allocated_quantity), "shortage_quantity": str(record.shortage_quantity), "state": record.state} for record in records]}


@app.post("/allocations/cancel")
def cancel_order_allocation(payload: AllocationCancellationRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    detail = session.get(OrderDetail, payload.order_detail_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Order detail not found")
    records = cancel_allocations(session, detail)
    session.commit()
    return {"detail_state": detail.state, "returned": [{"warehouse": record.warehouse, "quantity": str(record.allocated_quantity)} for record in records]}

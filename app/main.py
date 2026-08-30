from datetime import datetime, timezone
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import Base, engine, get_session
from app.models import Customer, Item, Order, OrderDetail, PriceAgreement
from app.schemas import CustomerCreate, ItemCreate, OrderCreate, PriceAgreementCreate
from app.services.pricing import resolve_price

app = FastAPI(title="Legacy Modernization API", version="0.3.0")


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
        if price is None:
            hold = True
        resolved_details.append((detail, price, basis, version))

    next_number = (session.scalar(select(func.max(Order.order_number))) or 0) + 1
    order = Order(order_number=next_number, customer_id=payload.customer_id, order_date=payload.order_date, delivery_date=payload.delivery_date, channel=payload.channel, state="price_unset_hold" if hold else "ready", total_amount=Decimal("0"))
    session.add(order)
    session.flush()
    total = Decimal("0")
    for line_number, (detail, price, basis, version) in enumerate(resolved_details, start=1):
        amount = price * detail.quantity if price is not None else None
        if amount is not None:
            total += amount
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
    return {"order_number": order.order_number, "state": order.state, "total_amount": str(order.total_amount), "details": [{"line_number": d.line_number, "item_id": d.item_id, "quantity": str(d.quantity), "unit_price": str(d.unit_price) if d.unit_price is not None else None, "amount": str(d.amount) if d.amount is not None else None, "state": d.state, "price_basis_type": d.price_basis_type, "price_agreement_version": d.price_agreement_version, "manual_difference_reason": d.manual_difference_reason} for d in details]}

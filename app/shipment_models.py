from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Shipment(Base):
    __tablename__ = "shipments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    shipment_number: Mapped[int] = mapped_column(nullable=False, unique=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    shipment_date: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="awaiting_confirmation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShipmentDetail(Base):
    __tablename__ = "shipment_details"
    __table_args__ = (UniqueConstraint("shipment_id", "order_detail_id", name="uq_shipment_detail_order_detail"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.id"), nullable=False)
    order_detail_id: Mapped[str] = mapped_column(ForeignKey("order_details.id"), nullable=False)
    warehouse: Mapped[str] = mapped_column(String(64), nullable=False)
    shipped_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    sales_posting_state: Mapped[str] = mapped_column(String(32), nullable=False, default="awaiting_confirmation")
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ShipmentConfirmation(Base):
    __tablename__ = "shipment_confirmations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    shipment_detail_id: Mapped[str] = mapped_column(ForeignKey("shipment_details.id"), nullable=False)
    confirmed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    action: Mapped[str] = mapped_column(String(24), nullable=False)

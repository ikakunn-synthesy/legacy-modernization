from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, LargeBinary, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LegacyFileImport(Base):
    __tablename__ = "legacy_file_imports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_format: Mapped[str] = mapped_column(String(16), nullable=False)
    declared_encoding: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="accepted")
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConversionSetting(Base):
    __tablename__ = "conversion_settings"
    __table_args__ = (UniqueConstraint("source_system", "file_type", name="uq_conversion_setting_scope"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    file_type: Mapped[str] = mapped_column(String(64), nullable=False)
    encoding: Mapped[str] = mapped_column(String(32), nullable=False)


class ConversionRecord(Base):
    __tablename__ = "conversion_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    import_id: Mapped[str] = mapped_column(ForeignKey("legacy_file_imports.id"), nullable=False)
    source_value: Mapped[str] = mapped_column(Text, nullable=False)
    standard_value: Mapped[str] = mapped_column(Text, nullable=False)
    conversion_rule: Mapped[str] = mapped_column(String(128), nullable=False)
    converted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MigrationException(Base):
    __tablename__ = "migration_exceptions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    import_id: Mapped[str] = mapped_column(ForeignKey("legacy_file_imports.id"), nullable=False)
    source_record: Mapped[str] = mapped_column(Text, nullable=False)
    failure_reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    corrected_value: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ItemCodeCorrespondence(Base):
    __tablename__ = "item_code_correspondences"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    legacy_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    standard_identifier: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="mapped")


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sales_terms: Mapped[str | None] = mapped_column(Text)
    credit_limit: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    tax_treatment: Mapped[str | None] = mapped_column(String(32))
    customer_rank: Mapped[int | None] = mapped_column()
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class Item(Base):
    __tablename__ = "items"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    classification: Mapped[str] = mapped_column(String(64), nullable=False)
    pricing: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    lot_rule: Mapped[str | None] = mapped_column(String(128))
    warehouse: Mapped[str | None] = mapped_column(String(64))
    tax_category: Mapped[str | None] = mapped_column(String(32))
    discontinued_state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    sales_owned_fields: Mapped[str | None] = mapped_column(Text)
    production_owned_fields: Mapped[str | None] = mapped_column(Text)


class PriceAgreement(Base):
    __tablename__ = "price_agreements"
    __table_args__ = (UniqueConstraint("customer_id", "item_id", "version", name="uq_price_agreement_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date] = mapped_column(Date, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    price_type: Mapped[str] = mapped_column(String(16), nullable=False, default="individual")
    campaign_classification: Mapped[str | None] = mapped_column(String(64))
    minimum_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 3))
    customer_rank: Mapped[int | None] = mapped_column()
    version: Mapped[int] = mapped_column(nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    order_number: Mapped[int] = mapped_column(nullable=False, unique=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrderDetail(Base):
    __tablename__ = "order_details"
    __table_args__ = (UniqueConstraint("order_id", "line_number", name="uq_order_detail_line"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    line_number: Mapped[int] = mapped_column(nullable=False)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    warehouse: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    price_basis_type: Mapped[str | None] = mapped_column(String(32))
    price_agreement_version: Mapped[int | None] = mapped_column()
    manual_difference_reason: Mapped[str | None] = mapped_column(Text)


class InventoryClassificationConversion(Base):
    __tablename__ = "inventory_classification_conversions"
    __table_args__ = (UniqueConstraint("source_system", "source_classification", name="uq_inventory_classification_mapping"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    source_classification: Mapped[str] = mapped_column(String(64), nullable=False)
    common_classification: Mapped[str] = mapped_column(String(64), nullable=False)
    conversion_rule: Mapped[str] = mapped_column(String(128), nullable=False)
    converted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InventoryClassificationReview(Base):
    __tablename__ = "inventory_classification_reviews"
    __table_args__ = (UniqueConstraint("source_system", "source_transaction", name="uq_inventory_review_source"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    source_transaction: Mapped[str] = mapped_column(String(128), nullable=False)
    source_classification: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_common_classification: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="review_required")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InventoryLedgerEntry(Base):
    __tablename__ = "inventory_ledger_entries"
    __table_args__ = (UniqueConstraint("source_system", "source_transaction", name="uq_inventory_ledger_source"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    source_transaction: Mapped[str] = mapped_column(String(128), nullable=False)
    source_classification: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    quantity_precision: Mapped[int] = mapped_column(nullable=False)
    common_classification: Mapped[str] = mapped_column(String(64), nullable=False)
    resulting_balance: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

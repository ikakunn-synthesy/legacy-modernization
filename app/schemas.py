from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class LegacyImportRequest(BaseModel):
    source_system: Literal["sales", "production", "accounting"]
    file_name: str
    file_format: Literal["csv", "fixed"]
    declared_encoding: str
    content_base64: str


class CustomerCreate(BaseModel):
    id: str
    name: str
    sales_terms: str | None = None
    credit_limit: Decimal | None = None
    tax_treatment: str | None = None
    state: Literal["active", "deleted"] = "active"


class ItemCreate(BaseModel):
    id: str
    classification: str
    pricing: Decimal | None = None
    lot_rule: str | None = None
    warehouse: str | None = None
    tax_category: str | None = None
    discontinued_state: Literal["active", "discontinued"] = "active"
    sales_owned_fields: str | None = None
    production_owned_fields: str | None = None


class PriceAgreementCreate(BaseModel):
    customer_id: str
    item_id: str
    effective_from: date
    effective_to: date
    price: Decimal
    campaign_classification: str | None = None


class InventoryMappingCreate(BaseModel):
    source_system: Literal["sales", "production"]
    source_classification: str
    common_classification: str
    conversion_rule: str


class InventoryLedgerEntryCreate(BaseModel):
    source_system: Literal["sales", "production"]
    source_transaction: str
    source_classification: str
    quantity: Decimal
    quantity_precision: int = Field(ge=0, le=6)
    common_classification: str
    resulting_balance: Decimal


class MigrationExceptionCorrection(BaseModel):
    corrected_value: str

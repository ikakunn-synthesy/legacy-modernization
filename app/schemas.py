from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CustomerCreate(BaseModel):
    id: str
    name: str
    sales_terms: str | None = None
    credit_limit: Decimal | None = None
    tax_treatment: str | None = None
    customer_rank: int | None = Field(default=None, ge=1, le=5)
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
    price_type: Literal["individual", "campaign", "lot", "rank"] = "individual"
    campaign_classification: str | None = None
    minimum_quantity: Decimal | None = None
    customer_rank: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def validate_price_type(self):
        if self.price_type == "lot" and self.minimum_quantity is None:
            raise ValueError("Lot price requires minimum_quantity")
        if self.price_type == "rank" and self.customer_rank is None:
            raise ValueError("Rank price requires customer_rank")
        return self


class OrderDetailCreate(BaseModel):
    item_id: str
    quantity: Decimal = Field(gt=0)
    delivery_date: date
    warehouse: str
    manual_price: Decimal | None = None
    manual_difference_reason: str | None = None


class OrderCreate(BaseModel):
    customer_id: str
    order_date: date
    delivery_date: date
    channel: Literal["standard", "edi", "web"]
    details: list[OrderDetailCreate] = Field(min_length=1)


class InventoryBalanceUpdate(BaseModel):
    warehouse: str
    item_id: str
    quantity_change: Decimal
    source_system: Literal["sales", "production"]
    source_transaction: str
    source_classification: str


class InventoryMappingCreate(BaseModel):
    source_system: Literal["sales", "production"]
    source_classification: str
    common_classification: Literal["finished_goods", "work_in_process", "raw_materials", "subcontract_supplied"]
    conversion_rule: str


class AllocationRequest(BaseModel):
    order_detail_id: str


class AllocationCancellationRequest(BaseModel):
    order_detail_id: str

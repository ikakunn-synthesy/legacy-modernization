from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class ShipmentLineCreate(BaseModel):
    order_detail_id: str
    warehouse: str
    shipped_quantity: Decimal = Field(gt=0)


class ShipmentCreate(BaseModel):
    order_id: str
    shipment_date: date
    details: list[ShipmentLineCreate] = Field(min_length=1)


class ShipmentConfirmationCreate(BaseModel):
    confirmed_by: str


class ShipmentCancellationCreate(BaseModel):
    cancelled_by: str

from decimal import Decimal

from app.models import AllocationRecord


def test_allocation_quantities_use_three_decimal_places() -> None:
    record = AllocationRecord(order_detail_id="detail", warehouse="A", allocated_quantity=Decimal("1.234"), shortage_quantity=Decimal("0.001"), state="allocated", action="allocated")
    assert record.allocated_quantity == Decimal("1.234")
    assert record.shortage_quantity == Decimal("0.001")

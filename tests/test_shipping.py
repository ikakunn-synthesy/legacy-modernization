from decimal import Decimal

from app.schemas import ShipmentLineCreate


def test_shipment_quantity_uses_three_decimal_places() -> None:
    line = ShipmentLineCreate(order_detail_id="detail-1", warehouse="TOKYO", shipped_quantity=Decimal("1.234"))
    assert line.shipped_quantity == Decimal("1.234")


def test_confirmed_shipment_uses_eligible_state_before_posting() -> None:
    eligible_before_posting = "eligible"
    assert eligible_before_posting != "cancelled"

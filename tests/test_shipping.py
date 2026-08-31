from decimal import Decimal

from app.schemas import ShipmentLineCreate


def test_shipment_quantity_uses_three_decimal_places() -> None:
    line = ShipmentLineCreate(order_detail_id="detail-1", warehouse="TOKYO", shipped_quantity=Decimal("1.234"))
    assert line.shipped_quantity == Decimal("1.234")

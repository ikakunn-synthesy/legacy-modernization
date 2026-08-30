from decimal import Decimal

from app.schemas import InventoryBalanceUpdate


def test_inventory_balance_update_requires_source_metadata() -> None:
    update = InventoryBalanceUpdate(
        warehouse="TOKYO",
        item_id="ITEM-1",
        quantity_change=Decimal("10.000"),
        source_system="production",
        source_transaction="production:receipt:1",
        source_classification="completed",
    )
    assert update.source_transaction == "production:receipt:1"

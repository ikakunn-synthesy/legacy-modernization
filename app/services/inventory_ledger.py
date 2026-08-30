from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InventoryClassificationConversion, InventoryClassificationReview, InventoryLedgerEntry


def record_inventory_update(
    session: Session,
    *,
    source_system: str,
    source_transaction: str,
    source_classification: str,
    quantity: Decimal,
    resulting_balance: Decimal,
) -> bool:
    mapping = session.scalar(
        select(InventoryClassificationConversion).where(
            InventoryClassificationConversion.source_system == source_system,
            InventoryClassificationConversion.source_classification == source_classification,
        )
    )
    if mapping is None:
        review = session.scalar(
            select(InventoryClassificationReview).where(
                InventoryClassificationReview.source_system == source_system,
                InventoryClassificationReview.source_transaction == source_transaction,
            )
        )
        if review is None:
            session.add(
                InventoryClassificationReview(
                    source_system=source_system,
                    source_transaction=source_transaction,
                    source_classification=source_classification,
                    requested_common_classification="finished_goods",
                    reason="No approved inventory classification mapping exists",
                )
            )
        return False
    session.add(
        InventoryLedgerEntry(
            source_system=source_system,
            source_transaction=source_transaction,
            source_classification=source_classification,
            quantity=quantity,
            quantity_precision=3,
            common_classification=mapping.common_classification,
            resulting_balance=resulting_balance,
        )
    )
    return True

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, Item, PriceAgreement


@dataclass(frozen=True)
class ResolvedPrice:
    price: Decimal | None
    basis_type: str | None
    agreement_version: int | None


def resolve_price(session: Session, customer_id: str, item_id: str, quantity: Decimal, order_date: date) -> ResolvedPrice:
    customer = session.get(Customer, customer_id)
    agreements = list(session.scalars(select(PriceAgreement).where(PriceAgreement.customer_id == customer_id, PriceAgreement.item_id == item_id, PriceAgreement.effective_from <= order_date, PriceAgreement.effective_to >= order_date).order_by(PriceAgreement.changed_at.desc())))
    individual = next((a for a in agreements if a.price_type == "individual"), None)
    if individual:
        return ResolvedPrice(individual.price, "individual", individual.version)
    campaign = next((a for a in agreements if a.price_type == "campaign"), None)
    if campaign:
        return ResolvedPrice(campaign.price, "campaign", campaign.version)
    lot = next((a for a in sorted((a for a in agreements if a.price_type == "lot" and a.minimum_quantity is not None and quantity >= a.minimum_quantity), key=lambda a: a.minimum_quantity or Decimal(0), reverse=True)), None)
    if lot:
        return ResolvedPrice(lot.price, "lot", lot.version)
    rank = next((a for a in agreements if a.price_type == "rank" and customer and a.customer_rank == customer.customer_rank), None)
    if rank:
        return ResolvedPrice(rank.price, "rank", rank.version)
    item = session.get(Item, item_id)
    if item and item.pricing is not None:
        return ResolvedPrice(item.pricing, "standard", None)
    return ResolvedPrice(None, None, None)

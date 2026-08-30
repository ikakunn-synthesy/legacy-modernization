from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Item, PriceAgreement


@dataclass(frozen=True)
class ResolvedPrice:
    price: Decimal | None
    basis_type: str | None
    agreement_version: int | None


def resolve_price(session: Session, customer_id: str, item_id: str, order_date: date) -> ResolvedPrice:
    agreements = list(session.scalars(select(PriceAgreement).where(PriceAgreement.customer_id == customer_id, PriceAgreement.item_id == item_id, PriceAgreement.effective_from <= order_date, PriceAgreement.effective_to >= order_date).order_by(PriceAgreement.changed_at.desc())))
    individual = next((agreement for agreement in agreements if agreement.campaign_classification is None), None)
    if individual:
        return ResolvedPrice(individual.price, "individual", individual.version)
    campaign = next((agreement for agreement in agreements if agreement.campaign_classification is not None), None)
    if campaign:
        return ResolvedPrice(campaign.price, "campaign", campaign.version)
    item = session.get(Item, item_id)
    if item and item.pricing is not None:
        return ResolvedPrice(item.pricing, "standard", None)
    return ResolvedPrice(None, None, None)

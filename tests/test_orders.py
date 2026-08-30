from datetime import date
from decimal import Decimal

from app.services.pricing import ResolvedPrice


def test_resolved_price_shape() -> None:
    price = ResolvedPrice(Decimal("100"), "individual", 2)
    assert price.basis_type == "individual"
    assert price.agreement_version == 2


def test_price_unset_shape() -> None:
    price = ResolvedPrice(None, None, None)
    assert price.price is None

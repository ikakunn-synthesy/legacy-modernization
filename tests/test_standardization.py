import pytest

from app.services.standardization import production_date_to_utc, sales_date_to_utc, standard_item_identifier


def test_item_identifier_uses_new_ten_character_rule() -> None:
    identifier = standard_item_identifier("1234567890")
    assert len(identifier) == 10
    assert identifier.startswith("123456789")


def test_sales_date_uses_japan_midnight_converted_to_utc() -> None:
    assert sales_date_to_utc("260101", 1) == "2025-12-31T15:00:00Z"


def test_production_date_uses_japan_midnight_converted_to_utc() -> None:
    assert production_date_to_utc("20260101") == "2025-12-31T15:00:00Z"


def test_short_item_code_is_not_a_standard_identifier() -> None:
    with pytest.raises(ValueError):
        standard_item_identifier("123")

import base64

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app
from app.services.importing import ImportDecodingError, decode_legacy_bytes, parse_fixed_width


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_decodes_cp932_without_replacement() -> None:
    raw = "得意先".encode("cp932")
    result = decode_legacy_bytes(raw, "cp932")
    assert result.text == "得意先"
    assert len(result.content_sha256) == 64


def test_rejects_invalid_encoding_bytes() -> None:
    with pytest.raises(ImportDecodingError):
        decode_legacy_bytes(b"\x81", "cp932")


def test_rejects_unknown_encoding() -> None:
    with pytest.raises(ImportDecodingError):
        decode_legacy_bytes(b"test", "iso-8859-1")


def test_parses_fixed_width_fields() -> None:
    records = parse_fixed_width("ABC 001", [("code", 0, 3), ("quantity", 4, 7)])
    assert records == [{"_line_number": "1", "code": "ABC", "quantity": "001"}]


def test_invalid_decoding_creates_migration_exception() -> None:
    client = TestClient(app)
    response = client.post(
        "/imports",
        json={
            "source_system": "sales",
            "file_name": "broken.csv",
            "file_format": "csv",
            "declared_encoding": "cp932",
            "content_base64": base64.b64encode(b"\x81").decode(),
        },
    )
    assert response.status_code == 422
    assert "migration_exception_id" in response.json()["detail"]


def test_inventory_entry_requires_mapping() -> None:
    client = TestClient(app)
    response = client.post(
        "/inventory-ledger-entries",
        json={
            "source_system": "sales",
            "source_transaction": "ORDER-1",
            "quantity": "1.000",
            "quantity_precision": 3,
            "common_classification": "finished_goods",
            "resulting_balance": "9.000",
        },
    )
    assert response.status_code == 422

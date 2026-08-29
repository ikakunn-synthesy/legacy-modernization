import pytest

from app.services.importing import ImportDecodingError, decode_legacy_bytes, parse_fixed_width


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

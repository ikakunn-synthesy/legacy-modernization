import codecs
import csv
import hashlib
from dataclasses import dataclass
from io import StringIO


SUPPORTED_ENCODINGS = {"utf-8", "cp932", "shift_jis", "euc_jp"}


class ImportDecodingError(ValueError):
    pass


@dataclass(frozen=True)
class DecodedLegacyFile:
    text: str
    content_sha256: str
    declared_encoding: str


def decode_legacy_bytes(content: bytes, declared_encoding: str) -> DecodedLegacyFile:
    encoding = declared_encoding.lower().replace("-", "_")
    aliases = {"utf_8": "utf-8", "shift_jis": "shift_jis", "cp932": "cp932", "euc_jp": "euc_jp"}
    encoding = aliases.get(encoding, encoding)
    if encoding not in SUPPORTED_ENCODINGS:
        raise ImportDecodingError(f"Unsupported declared encoding: {declared_encoding}")
    try:
        codecs.lookup(encoding)
        text = content.decode(encoding, errors="strict")
    except UnicodeDecodeError as exc:
        raise ImportDecodingError(f"Cannot decode {declared_encoding} without replacement: {exc}") from exc
    if "\ufffd" in text:
        raise ImportDecodingError("Replacement character is not allowed in imported text")
    return DecodedLegacyFile(
        text=text,
        content_sha256=hashlib.sha256(content).hexdigest(),
        declared_encoding=declared_encoding,
    )


def parse_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(StringIO(text)))


def parse_fixed_width(text: str, fields: list[tuple[str, int, int]]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        record: dict[str, str] = {"_line_number": str(line_number)}
        for name, start, end in fields:
            if start < 0 or end <= start:
                raise ValueError(f"Invalid field range for {name}")
            record[name] = line[start:end].strip()
        records.append(record)
    return records

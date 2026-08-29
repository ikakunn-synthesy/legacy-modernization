from datetime import datetime
from zoneinfo import ZoneInfo


JST = ZoneInfo("Asia/Tokyo")
COMMON_INVENTORY_CLASSIFICATIONS = {
    "finished_goods",
    "work_in_process",
    "raw_materials",
    "subcontract_supplied",
}


def new_item_check_digit(base9: str) -> str:
    if len(base9) != 9 or not base9.isalnum():
        raise ValueError("A standard item identifier requires a 9-character alphanumeric base")
    total = 0
    for index, character in enumerate(base9.upper()):
        value = int(character) if character.isdigit() else ord(character) - 55
        total += value * (3 if index % 2 == 0 else 1)
    return "XYZABCDEFG"[total % 10]


def standard_item_identifier(legacy_code: str) -> str:
    cleaned = legacy_code.strip().upper()
    if len(cleaned) < 9:
        raise ValueError("Legacy item code has no 9-character base")
    return cleaned[:9] + new_item_check_digit(cleaned[:9])


def sales_date_to_utc(value: str, century_flag: int) -> str:
    if len(value) != 6 or not value.isdigit() or century_flag not in {0, 1}:
        raise ValueError("Sales date must be YYMMDD with century flag 0 or 1")
    year = (2000 if century_flag == 1 else 1900) + int(value[:2])
    return datetime(year, int(value[2:4]), int(value[4:6]), tzinfo=JST).astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")


def production_date_to_utc(value: str) -> str:
    if len(value) != 8 or not value.isdigit():
        raise ValueError("Production date must be YYYYMMDD")
    return datetime(int(value[:4]), int(value[4:6]), int(value[6:8]), tzinfo=JST).astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")


def accounting_date_to_utc(value: str, era_year: int | None = None) -> str:
    if len(value) != 8 or not value.isdigit():
        raise ValueError("Accounting date requires a corrected Gregorian YYYYMMDD value")
    return production_date_to_utc(value)

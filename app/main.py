import base64
import hashlib
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base, engine, get_session
from app.models import (
    ConversionRecord,
    ConversionSetting,
    Customer,
    InventoryClassificationConversion,
    InventoryClassificationReview,
    InventoryLedgerEntry,
    Item,
    ItemCodeCorrespondence,
    LegacyFileImport,
    MigrationException,
    PriceAgreement,
)
from app.schemas import (
    ConversionSettingCreate,
    CustomerCreate,
    InventoryLedgerEntryCreate,
    InventoryMappingCreate,
    ItemCodeConvertRequest,
    ItemCreate,
    LegacyDateConvertRequest,
    LegacyImportRequest,
    MigrationExceptionCorrection,
    PriceAgreementCreate,
)
from app.services.importing import ImportDecodingError, decode_legacy_bytes
from app.services.standardization import accounting_date_to_utc, production_date_to_utc, sales_date_to_utc, standard_item_identifier

app = FastAPI(title="Legacy Modernization API", version="0.2.0")


@app.on_event("startup")
def create_schema() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/conversion-settings", status_code=status.HTTP_201_CREATED)
def save_conversion_setting(payload: ConversionSettingCreate, session: Session = Depends(get_session)) -> dict[str, str]:
    setting = session.scalar(select(ConversionSetting).where(ConversionSetting.source_system == payload.source_system, ConversionSetting.file_type == payload.file_type))
    if setting is None:
        setting = ConversionSetting(**payload.model_dump())
        session.add(setting)
    else:
        setting.encoding = payload.encoding
    session.commit()
    return {"id": setting.id, "encoding": setting.encoding}


@app.post("/imports", status_code=status.HTTP_201_CREATED)
def create_import(payload: LegacyImportRequest, session: Session = Depends(get_session)) -> dict[str, str]:
    try:
        raw = base64.b64decode(payload.content_base64, validate=True)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The import content is not valid Base64") from exc

    content_sha256 = hashlib.sha256(raw).hexdigest()
    existing = session.scalar(select(LegacyFileImport).where(LegacyFileImport.content_sha256 == content_sha256))
    if existing:
        return {"import_id": existing.id, "status": "duplicate"}

    setting = session.scalar(select(ConversionSetting).where(ConversionSetting.source_system == payload.source_system, ConversionSetting.file_type == payload.file_type))
    encoding = payload.declared_encoding or (setting.encoding if setting else None)
    if encoding is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No encoding default exists for this source system and file type")

    imported = LegacyFileImport(source_system=payload.source_system, file_name=payload.file_name, file_type=payload.file_type, file_format=payload.file_format, declared_encoding=encoding, raw_content=raw, content_sha256=content_sha256)
    session.add(imported)
    session.flush()
    try:
        decoded = decode_legacy_bytes(raw, encoding)
    except ImportDecodingError as exc:
        imported.status = "pending_encoding"
        exception = MigrationException(import_id=imported.id, source_record=payload.file_name, failure_reason=str(exc), status="pending_encoding")
        session.add(exception)
        session.commit()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"migration_exception_id": exception.id, "reason": exception.failure_reason, "alternative_encodings": ["utf-8", "cp932", "shift_jis", "euc_jp"]}) from exc

    if payload.declared_encoding and (setting is None or setting.encoding != encoding):
        if setting is None:
            session.add(ConversionSetting(source_system=payload.source_system, file_type=payload.file_type, encoding=encoding))
        else:
            setting.encoding = encoding

    for legacy_value in decoded.text.splitlines() or [decoded.text]:
        session.add(ConversionRecord(import_id=imported.id, source_value=legacy_value, standard_value=legacy_value, conversion_rule=f"decode:{decoded.declared_encoding}->utf-8"))
    session.commit()
    return {"import_id": imported.id, "status": "accepted"}


@app.post("/item-code-correspondences", status_code=status.HTTP_201_CREATED)
def convert_item_code(payload: ItemCodeConvertRequest, session: Session = Depends(get_session)) -> dict[str, str | None]:
    existing = session.scalar(select(ItemCodeCorrespondence).where(ItemCodeCorrespondence.legacy_code == payload.legacy_code))
    if existing:
        return {"legacy_code": existing.legacy_code, "standard_identifier": existing.standard_identifier, "status": existing.status}
    try:
        identifier = standard_item_identifier(payload.legacy_code)
        collision = session.scalar(select(ItemCodeCorrespondence).where(ItemCodeCorrespondence.standard_identifier == identifier))
        item = ItemCodeCorrespondence(legacy_code=payload.legacy_code, standard_identifier=identifier, status="review_required" if collision else "mapped")
    except ValueError:
        item = ItemCodeCorrespondence(legacy_code=payload.legacy_code, standard_identifier=None, status="unverified")
    session.add(item)
    session.commit()
    return {"legacy_code": item.legacy_code, "standard_identifier": item.standard_identifier, "status": item.status}


@app.post("/legacy-dates/convert")
def convert_legacy_date(payload: LegacyDateConvertRequest) -> dict[str, str]:
    try:
        if payload.source_system == "sales":
            if payload.century_flag is None:
                raise ValueError("Sales date requires century_flag")
            standard_value = sales_date_to_utc(payload.value, payload.century_flag)
        elif payload.source_system == "production":
            standard_value = production_date_to_utc(payload.value)
        else:
            if payload.corrected_gregorian_year is None:
                raise ValueError("Accounting-era date requires corrected_gregorian_year")
            standard_value = accounting_date_to_utc(f"{payload.corrected_gregorian_year:04d}{payload.value[-4:]}")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"standard_value": standard_value}


@app.post("/customers", status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, session: Session = Depends(get_session)) -> dict[str, str]:
    customer = Customer(**payload.model_dump())
    session.add(customer)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Customer already exists") from exc
    return {"id": customer.id}


@app.post("/items", status_code=status.HTTP_201_CREATED)
def create_item(payload: ItemCreate, session: Session = Depends(get_session)) -> dict[str, str]:
    item = Item(**payload.model_dump())
    session.add(item)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Item already exists") from exc
    return {"id": item.id}


@app.post("/price-agreements", status_code=status.HTTP_201_CREATED)
def create_price_agreement(payload: PriceAgreementCreate, session: Session = Depends(get_session)) -> dict[str, str | int]:
    if session.get(Customer, payload.customer_id) is None or session.get(Item, payload.item_id) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Customer and item must exist before a price agreement is created")
    latest_version = session.scalar(select(PriceAgreement.version).where(PriceAgreement.customer_id == payload.customer_id, PriceAgreement.item_id == payload.item_id).order_by(PriceAgreement.version.desc()).limit(1))
    agreement = PriceAgreement(**payload.model_dump(), version=(latest_version or 0) + 1)
    session.add(agreement)
    session.commit()
    return {"id": agreement.id, "version": agreement.version}


@app.post("/inventory-classification-mappings", status_code=status.HTTP_201_CREATED)
def create_inventory_mapping(payload: InventoryMappingCreate, session: Session = Depends(get_session)) -> dict[str, str]:
    mapping = InventoryClassificationConversion(**payload.model_dump())
    session.add(mapping)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A mapping already exists for this source classification") from exc
    return {"id": mapping.id}


@app.post("/inventory-ledger-entries", status_code=status.HTTP_201_CREATED)
def create_inventory_ledger_entry(payload: InventoryLedgerEntryCreate, session: Session = Depends(get_session)) -> dict[str, str]:
    mapping = session.scalar(select(InventoryClassificationConversion).where(InventoryClassificationConversion.source_system == payload.source_system, InventoryClassificationConversion.source_classification == payload.source_classification))
    if mapping is None or mapping.common_classification != payload.common_classification:
        review = InventoryClassificationReview(source_system=payload.source_system, source_transaction=payload.source_transaction, source_classification=payload.source_classification, requested_common_classification=payload.common_classification, reason="No approved inventory classification mapping exists")
        session.add(review)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This inventory update is already recorded or marked for review") from exc
        raise HTTPException(status_code=status.HTTP_202_ACCEPTED, detail={"review_id": review.id, "status": review.status})
    entry = InventoryLedgerEntry(**payload.model_dump())
    session.add(entry)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An inventory entry already exists for this source transaction") from exc
    return {"id": entry.id}


@app.post("/migration-exceptions/{exception_id}/correct")
def correct_migration_exception(exception_id: str, payload: MigrationExceptionCorrection, session: Session = Depends(get_session)) -> dict[str, str]:
    exception = session.get(MigrationException, exception_id)
    if exception is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Migration exception not found")
    exception.corrected_value = payload.corrected_value
    exception.status = "corrected"
    exception.resolved_at = datetime.now(timezone.utc)
    session.commit()
    return {"id": exception.id, "status": exception.status}

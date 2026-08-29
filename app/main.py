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
    Customer,
    InventoryClassificationConversion,
    InventoryClassificationReview,
    InventoryLedgerEntry,
    Item,
    LegacyFileImport,
    MigrationException,
    PriceAgreement,
)
from app.schemas import (
    CustomerCreate,
    InventoryLedgerEntryCreate,
    InventoryMappingCreate,
    ItemCreate,
    LegacyImportRequest,
    MigrationExceptionCorrection,
    PriceAgreementCreate,
)
from app.services.importing import ImportDecodingError, decode_legacy_bytes

app = FastAPI(title="Legacy Modernization API", version="0.1.2")


@app.on_event("startup")
def create_schema() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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

    imported = LegacyFileImport(
        source_system=payload.source_system,
        file_name=payload.file_name,
        file_format=payload.file_format,
        declared_encoding=payload.declared_encoding,
        raw_content=raw,
        content_sha256=content_sha256,
    )
    session.add(imported)
    session.flush()

    try:
        decoded = decode_legacy_bytes(raw, payload.declared_encoding)
    except ImportDecodingError as exc:
        exception = MigrationException(
            import_id=imported.id,
            source_record=payload.file_name,
            failure_reason=str(exc),
            status="open",
        )
        session.add(exception)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"migration_exception_id": exception.id, "reason": exception.failure_reason},
        ) from exc

    raw_lines = raw.splitlines() or [raw]
    decoded_lines = decoded.text.splitlines() or [decoded.text]
    for raw_line, standard_value in zip(raw_lines, decoded_lines, strict=True):
        session.add(
            ConversionRecord(
                import_id=imported.id,
                source_value=f"base64:{base64.b64encode(raw_line).decode('ascii')}",
                standard_value=standard_value,
                conversion_rule=f"decode:{decoded.declared_encoding}->utf-8",
            )
        )
    session.commit()
    return {"import_id": imported.id, "status": "accepted"}


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
    latest_version = session.scalar(
        select(PriceAgreement.version)
        .where(PriceAgreement.customer_id == payload.customer_id, PriceAgreement.item_id == payload.item_id)
        .order_by(PriceAgreement.version.desc())
        .limit(1)
    )
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
    mapping = session.scalar(
        select(InventoryClassificationConversion).where(
            InventoryClassificationConversion.source_system == payload.source_system,
            InventoryClassificationConversion.source_classification == payload.source_classification,
        )
    )
    if mapping is None or mapping.common_classification != payload.common_classification:
        review = InventoryClassificationReview(
            source_system=payload.source_system,
            source_transaction=payload.source_transaction,
            source_classification=payload.source_classification,
            requested_common_classification=payload.common_classification,
            reason="No approved inventory classification mapping exists",
        )
        session.add(review)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This inventory update is already recorded or marked for review") from exc
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail={"review_id": review.id, "status": review.status},
        )
    entry = InventoryLedgerEntry(**payload.model_dump())
    session.add(entry)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An inventory entry already exists for this source transaction") from exc
    return {"id": entry.id}


@app.post("/migration-exceptions/{exception_id}/correct")
def correct_migration_exception(
    exception_id: str,
    payload: MigrationExceptionCorrection,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    exception = session.get(MigrationException, exception_id)
    if exception is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Migration exception not found")
    exception.corrected_value = payload.corrected_value
    exception.status = "corrected"
    exception.resolved_at = datetime.now(timezone.utc)
    session.commit()
    return {"id": exception.id, "status": exception.status}

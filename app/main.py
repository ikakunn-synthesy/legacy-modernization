import base64
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base, engine, get_session
from app.models import (
    InventoryClassificationConversion,
    InventoryLedgerEntry,
    LegacyFileImport,
    MigrationException,
    PriceAgreement,
)
from app.schemas import (
    InventoryLedgerEntryCreate,
    InventoryMappingCreate,
    LegacyImportRequest,
    PriceAgreementCreate,
)
from app.services.importing import ImportDecodingError, decode_legacy_bytes

app = FastAPI(title="Legacy Modernization API", version="0.1.0")


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
        decoded = decode_legacy_bytes(raw, payload.declared_encoding)
    except (ValueError, ImportDecodingError) as exc:
        exception = MigrationException(
            import_id="unpersisted",
            source_record=payload.file_name,
            failure_reason=str(exc),
            status="open",
        )
        # The raw import cannot be persisted without a valid decoded record; report the failure to the caller.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exception.failure_reason) from exc

    existing = session.scalar(select(LegacyFileImport).where(LegacyFileImport.content_sha256 == decoded.content_sha256))
    if existing:
        return {"import_id": existing.id, "status": "duplicate"}

    imported = LegacyFileImport(
        source_system=payload.source_system,
        file_name=payload.file_name,
        file_format=payload.file_format,
        declared_encoding=decoded.declared_encoding,
        content_sha256=decoded.content_sha256,
    )
    session.add(imported)
    session.commit()
    return {"import_id": imported.id, "status": "accepted"}


@app.post("/price-agreements", status_code=status.HTTP_201_CREATED)
def create_price_agreement(payload: PriceAgreementCreate, session: Session = Depends(get_session)) -> dict[str, str | int]:
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
    entry = InventoryLedgerEntry(**payload.model_dump())
    session.add(entry)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An inventory entry already exists for this source transaction") from exc
    return {"id": entry.id}


@app.post("/migration-exceptions/{exception_id}/correct")
def correct_migration_exception(exception_id: str, corrected_value: str, session: Session = Depends(get_session)) -> dict[str, str]:
    exception = session.get(MigrationException, exception_id)
    if exception is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Migration exception not found")
    exception.corrected_value = corrected_value
    exception.status = "corrected"
    exception.resolved_at = datetime.now(timezone.utc)
    session.commit()
    return {"id": exception.id, "status": exception.status}

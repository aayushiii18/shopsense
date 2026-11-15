"""
services/etl/batch_manager.py — Orchestrator for bulk CSV ingestion, staging, validation, loading, and auditing.

Coordinates the end-to-end pipeline:
  Extract → Stage → Validate → Deduplicate → Quarantine / Load → Reconcile → Audit
"""

import io
import time
import uuid
import json
from datetime import datetime
from typing import BinaryIO, Dict, Any, List, Optional, Tuple, Set
from sqlalchemy.orm import Session

from app.models.etl import ETLBatch, ETLStagingRecord, ETLQuarantineRecord
from app.models.product import Product
from app.models.vendor import Vendor
from app.models.customer import Customer
from app.models.transaction import Transaction

from app.services.etl.extract import extract_chunks, compute_file_hash, normalize_headers
from app.services.etl.validation import validate_row, ValidationResult
from app.services.etl.quarantine import create_quarantine_record
from app.services.etl.deduplication import deduplicate_chunk
from app.services.etl.transformation import transform_transaction_record
from app.services.etl.loading import load_transactions_chunk
from app.services.etl.reconciliation import reconcile_batch
from app.services.etl.daily_mart_service import refresh_daily_sales_mart


def create_batch(
    db: Session,
    filename: str,
    file_bytes: bytes,
    source_system: str = "CSV_INGEST",
) -> ETLBatch:
    """Creates a new ETLBatch in RECEIVED status."""
    batch_uuid = f"batch-{uuid.uuid4().hex[:12]}"
    f_hash = compute_file_hash(file_bytes)

    batch = ETLBatch(
        batch_id=batch_uuid,
        source_system=source_system,
        original_filename=filename,
        file_size_bytes=len(file_bytes),
        file_hash=f_hash,
        status="RECEIVED",
        total_records=0,
        staged_records=0,
        committed_records=0,
        duplicate_records=0,
        quarantined_records=0,
        failed_records=0,
        total_gross_value=0.0,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def process_csv_batch(
    db: Session,
    batch_id: str,
    file_stream: BinaryIO,
    chunk_size: int = 1000,
    custom_mapping: Optional[Dict[str, str]] = None,
    sync_inventory: bool = False,
    refresh_marts: bool = True,
) -> Dict[str, Any]:
    """
    Executes the streaming ingestion pipeline for the specified batch.
    Processes data in chunks to prevent unbounded memory growth.
    """
    batch = db.query(ETLBatch).filter(ETLBatch.batch_id == batch_id).first()
    if not batch:
        raise ValueError(f"Batch {batch_id} not found.")

    batch.status = "PROCESSING"
    batch.started_at = datetime.utcnow()
    db.commit()

    t_start = time.time()
    seen_in_batch: Set[str] = set()
    affected_dates: Set[datetime.date] = set()

    # Pre-fetch catalog sets once for fast in-memory validation
    products = db.query(Product.id, Product.vendor_id).all()
    valid_product_ids = {p.id for p in products}
    product_vendor_map = {p.id: p.vendor_id for p in products}
    valid_vendor_ids = {v.id for v in db.query(Vendor.id).all()}
    valid_customer_ids = {c.customer_id for c in db.query(Customer.customer_id).all()}

    # Vendor commission map for financial snapshotting
    vendor_commissions = {
        v.id: getattr(v, "commission_rate", 0.12)
        for v in db.query(Vendor).all()
    }

    total_records = 0
    staged_records = 0
    committed_records = 0
    duplicate_records = 0
    quarantined_records = 0
    failed_records = 0
    total_gross_val = 0.0

    try:
        for chunk_idx, raw_chunk, header_map in extract_chunks(
            file_stream=file_stream,
            chunk_size=chunk_size,
            custom_mapping=custom_mapping,
        ):
            # 1. Stage raw rows
            staged_entities: List[Tuple[ETLStagingRecord, Dict[str, Any]]] = []
            for item in raw_chunk:
                total_records += 1
                staged_records += 1
                row_num = item["_row_number"]
                raw_payload = item["_raw_payload"]
                src_tx_id = item.get("source_transaction_id")

                stg = ETLStagingRecord(
                    batch_id=batch_id,
                    row_number=row_num,
                    source_transaction_id=str(src_tx_id) if src_tx_id else None,
                    raw_payload=json.dumps(raw_payload),
                    status="STAGED",
                )
                db.add(stg)
                staged_entities.append((stg, item))

            db.flush()  # assign staging_id

            # 2. Validate rows in chunk
            valid_for_dedup: List[Tuple[Dict[str, Any], int, int]] = []
            # (cleaned_record, row_number, staging_id)

            for stg, item in staged_entities:
                val_res: ValidationResult = validate_row(
                    row=item,
                    valid_product_ids=valid_product_ids,
                    valid_vendor_ids=valid_vendor_ids,
                    valid_customer_ids=valid_customer_ids,
                    product_vendor_map=product_vendor_map,
                )

                if val_res.is_valid:
                    val_res.cleaned_record["_row_number"] = item["_row_number"]
                    val_res.cleaned_record["_staging_id"] = stg.staging_id
                    stg.status = "VALIDATED"
                    valid_for_dedup.append((val_res.cleaned_record, item["_row_number"], stg.staging_id))
                else:
                    # Quarantine invalid record
                    quarantined_records += 1
                    stg.status = "QUARANTINED"
                    stg.validation_errors = json.dumps(val_res.errors)

                    create_quarantine_record(
                        db=db,
                        batch_id=batch_id,
                        row_number=item["_row_number"],
                        source_transaction_id=item.get("source_transaction_id"),
                        error_category=val_res.error_category,
                        error_details=val_res.errors,
                        raw_payload=item["_raw_payload"],
                        staging_id=stg.staging_id,
                    )

            # 3. Deduplicate valid rows
            if valid_for_dedup:
                records_to_dedup = [t[0] for t in valid_for_dedup]
                # Map source_id/row to staging_id
                staging_lookup = {
                    (t[1], str(t[0].get("source_transaction_id"))): t[2]
                    for t in valid_for_dedup
                }

                dedup_res = deduplicate_chunk(
                    db=db,
                    records=records_to_dedup,
                    source_system=batch.source_system,
                    seen_in_batch=seen_in_batch,
                )

                # Mark duplicates
                for dup_info in dedup_res.duplicate_records:
                    duplicate_records += 1
                    dup_rec = dup_info["record"]
                    row_no = dup_rec.get("_row_number", 0)
                    stg_id = dup_rec.get("_staging_id") or staging_lookup.get((row_no, str(dup_rec.get("source_transaction_id"))))
                    if stg_id:
                        dup_stg = db.query(ETLStagingRecord).filter(ETLStagingRecord.staging_id == stg_id).first()
                        if dup_stg:
                            dup_stg.status = "DUPLICATE"
                            dup_stg.validation_errors = dup_info["reason"]

                # 4. Transform unique valid records
                transform_ready: List[Tuple[Dict[str, Any], int, Optional[int]]] = []
                for uniq in dedup_res.unique_records:
                    row_no = uniq.get("_row_number", 0)
                    stg_id = uniq.get("_staging_id") or staging_lookup.get((row_no, str(uniq.get("source_transaction_id"))))

                    transformed = transform_transaction_record(
                        record=uniq,
                        vendor_commission_map=vendor_commissions,
                        source_system=batch.source_system,
                    )
                    transform_ready.append((transformed, row_no, stg_id))

                    if transformed.get("transaction_date"):
                        affected_dates.add(transformed["transaction_date"].date())

                # 5. Load chunk into operational database
                if transform_ready:
                    loaded_txns, chunk_gmv = load_transactions_chunk(
                        db=db,
                        transformed_records=transform_ready,
                        sync_inventory=sync_inventory,
                    )
                    committed_records += len(loaded_txns)
                    total_gross_val += chunk_gmv

            db.commit()

        # Determine final status
        if committed_records > 0 and quarantined_records == 0 and duplicate_records == 0 and failed_records == 0:
            final_status = "COMPLETED"
        elif committed_records > 0:
            final_status = "PARTIALLY_COMPLETED"
        elif total_records == 0:
            final_status = "COMPLETED"
        else:
            final_status = "FAILED"

    except Exception as e:
        db.rollback()
        final_status = "FAILED"
        batch.error_summary = f"Pipeline execution aborted: {str(e)}"
        batch.status = "FAILED"
        batch.completed_at = datetime.utcnow()
        batch.processing_duration_ms = round((time.time() - t_start) * 1000, 2)
        db.commit()
        raise

    duration_ms = round((time.time() - t_start) * 1000, 2)

    # Update final batch audit metrics
    batch.status = final_status
    batch.total_records = total_records
    batch.staged_records = staged_records
    batch.committed_records = committed_records
    batch.duplicate_records = duplicate_records
    batch.quarantined_records = quarantined_records
    batch.failed_records = failed_records
    batch.total_gross_value = round(total_gross_val, 2)
    batch.processing_duration_ms = duration_ms
    batch.completed_at = datetime.utcnow()
    db.commit()

    # 6. Optional incremental daily mart refresh for affected dates
    if refresh_marts and affected_dates:
        min_date = min(affected_dates)
        max_date = max(affected_dates)
        refresh_daily_sales_mart(db=db, start_date=min_date, end_date=max_date, full_rebuild=False)

    # 7. Generate reconciliation report
    recon_report = reconcile_batch(db, batch_id)

    return {
        "batch_id": batch.batch_id,
        "status": batch.status,
        "total_records": total_records,
        "committed_records": committed_records,
        "duplicate_records": duplicate_records,
        "quarantined_records": quarantined_records,
        "failed_records": failed_records,
        "total_gross_value": round(total_gross_val, 2),
        "processing_duration_ms": duration_ms,
        "reconciliation": recon_report,
    }


def list_batches(
    db: Session,
    status: Optional[str] = None,
    source_system: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """Retrieves paginated ETL batches."""
    q = db.query(ETLBatch)
    if status:
        q = q.filter(ETLBatch.status == status)
    if source_system:
        q = q.filter(ETLBatch.source_system == source_system)

    total_count = q.count()
    records = q.order_by(ETLBatch.created_at.desc()).offset(offset).limit(limit).all()
    return [r.to_dict() for r in records], total_count


def get_batch(db: Session, batch_id: str) -> Optional[ETLBatch]:
    """Retrieves single ETL batch by batch_id."""
    return db.query(ETLBatch).filter(ETLBatch.batch_id == batch_id).first()


def list_batch_staging_records(
    db: Session,
    batch_id: str,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """Retrieves staged records belonging to a batch."""
    q = db.query(ETLStagingRecord).filter(ETLStagingRecord.batch_id == batch_id)
    if status:
        q = q.filter(ETLStagingRecord.status == status)

    total_count = q.count()
    records = q.order_by(ETLStagingRecord.row_number.asc()).offset(offset).limit(limit).all()
    return [r.to_dict() for r in records], total_count

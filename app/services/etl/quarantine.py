"""
services/etl/quarantine.py — Quarantine storage, inspection, correction, and reprocessing workflow.

Provides:
  - create_quarantine_record: Inserts an invalid row into etl_quarantine_records.
  - list_quarantine_records: Retrieves quarantined rows with status, batch, and category filters.
  - get_quarantine_record: Retrieves single quarantined record with full audit context.
  - reprocess_quarantine_record: Re-evaluates a quarantined row with optional manual corrections.
  - reprocess_batch_quarantine: Retries all pending quarantine entries for an entire batch.
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.models.etl import ETLBatch, ETLStagingRecord, ETLQuarantineRecord
from app.models.product import Product
from app.models.vendor import Vendor
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.services.etl.validation import validate_row, ValidationResult


def create_quarantine_record(
    db: Session,
    batch_id: str,
    row_number: int,
    source_transaction_id: Optional[str],
    error_category: str,
    error_details: List[str] | str,
    raw_payload: Dict[str, Any] | str,
    staging_id: Optional[int] = None,
) -> ETLQuarantineRecord:
    """Creates and persists an ETLQuarantineRecord."""
    details_str = json.dumps(error_details) if isinstance(error_details, list) else str(error_details)
    raw_str = json.dumps(raw_payload) if isinstance(raw_payload, dict) else str(raw_payload)

    record = ETLQuarantineRecord(
        staging_id=staging_id,
        batch_id=batch_id,
        row_number=row_number,
        source_transaction_id=str(source_transaction_id) if source_transaction_id else None,
        error_category=error_category,
        error_details=details_str,
        raw_data=raw_str,
        resolution_status="PENDING",
        reprocessing_attempts=0,
    )
    db.add(record)
    return record


def list_quarantine_records(
    db: Session,
    batch_id: Optional[str] = None,
    resolution_status: Optional[str] = None,
    error_category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """Retrieves paginated quarantine records with filtering."""
    q = db.query(ETLQuarantineRecord)
    if batch_id:
        q = q.filter(ETLQuarantineRecord.batch_id == batch_id)
    if resolution_status:
        q = q.filter(ETLQuarantineRecord.resolution_status == resolution_status)
    if error_category:
        q = q.filter(ETLQuarantineRecord.error_category == error_category)

    total_count = q.count()
    records = q.order_by(ETLQuarantineRecord.created_at.desc()).offset(offset).limit(limit).all()
    return [r.to_dict() for r in records], total_count


def get_quarantine_record(db: Session, quarantine_id: int) -> Optional[ETLQuarantineRecord]:
    """Retrieves single quarantine record by primary key."""
    return db.query(ETLQuarantineRecord).filter(ETLQuarantineRecord.quarantine_id == quarantine_id).first()


def reprocess_quarantine_record(
    db: Session,
    quarantine_id: int,
    corrected_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Attempts to reprocess a quarantined record.
    If `corrected_data` is supplied, it overrides/merges with raw_data.
    """
    rec = get_quarantine_record(db, quarantine_id)
    if not rec:
        return {"success": False, "message": f"Quarantine record {quarantine_id} not found."}

    if rec.resolution_status == "RESOLVED":
        return {"success": False, "message": f"Quarantine record {quarantine_id} is already resolved."}

    rec.reprocessing_attempts += 1
    rec.last_reprocessed_at = datetime.utcnow()

    # Load base raw payload
    try:
        payload = json.loads(rec.raw_data) if isinstance(rec.raw_data, str) else dict(rec.raw_data)
    except Exception:
        payload = {}

    # Merge manual corrections
    if corrected_data:
        payload.update(corrected_data)
        rec.raw_data = json.dumps(payload)

    # Fetch reference catalogs
    valid_pids = {p[0] for p in db.query(Product.id).all()}
    valid_vids = {v[0] for v in db.query(Vendor.id).all()}
    valid_cids = {c[0] for c in db.query(Customer.customer_id).all()}

    val_res = validate_row(
        row=payload,
        valid_product_ids=valid_pids,
        valid_vendor_ids=valid_vids,
        valid_customer_ids=valid_cids,
    )

    if not val_res.is_valid:
        rec.error_details = json.dumps(val_res.errors)
        rec.error_category = val_res.error_category
        db.commit()
        return {
            "success": False,
            "message": "Record validation failed upon reprocessing.",
            "errors": val_res.errors,
            "reprocessing_attempts": rec.reprocessing_attempts,
        }

    # Deduplication check
    cleaned = val_res.cleaned_record
    src_sys = "CSV_INGEST"
    batch = db.query(ETLBatch).filter(ETLBatch.batch_id == rec.batch_id).first()
    if batch:
        src_sys = batch.source_system

    src_tx_id = cleaned.get("source_transaction_id") or rec.source_transaction_id
    if src_tx_id:
        existing = (
            db.query(Transaction)
            .filter(
                Transaction.source_system == src_sys,
                Transaction.source_transaction_id == str(src_tx_id),
            )
            .first()
        )
        if existing:
            rec.error_category = "DUPLICATE_SOURCE_ID"
            rec.error_details = json.dumps([f"Transaction {src_tx_id} already exists in database (ID {existing.transaction_id})"])
            rec.resolution_status = "IGNORED"
            db.commit()
            return {
                "success": False,
                "message": f"Source transaction {src_tx_id} is a duplicate of committed transaction {existing.transaction_id}.",
                "existing_transaction_id": existing.transaction_id,
            }

    # Valid and unique -> Insert into production transactions
    # Fetch vendor commission rate snapshot
    vendor = db.query(Vendor).filter(Vendor.id == cleaned["vendor_id"]).first()
    commission_rate = vendor.commission_rate if vendor and hasattr(vendor, "commission_rate") else None

    txn = Transaction(
        product_id=cleaned["product_id"],
        vendor_id=cleaned["vendor_id"],
        customer_id=cleaned.get("customer_id"),
        quantity=cleaned["quantity"],
        unit_price=cleaned["unit_price"],
        amount=cleaned["amount"],
        discount_amount=cleaned.get("discount_amount", 0.0),
        payment_method=cleaned.get("payment_method", "UNKNOWN"),
        payment_status=cleaned.get("payment_status", "COMPLETED"),
        effective_commission_rate=commission_rate,
        source_system=src_sys,
        source_transaction_id=str(src_tx_id) if src_tx_id else None,
        transaction_date=cleaned.get("transaction_date", datetime.utcnow()),
    )
    db.add(txn)
    db.flush()

    # Update quarantine status
    rec.resolution_status = "RESOLVED"
    rec.source_transaction_id = str(src_tx_id) if src_tx_id else None

    # Update staging record if linked
    if rec.staging_id:
        stg = db.query(ETLStagingRecord).filter(ETLStagingRecord.staging_id == rec.staging_id).first()
        if stg:
            stg.status = "COMMITTED"
            stg.target_transaction_id = txn.transaction_id

    # Update batch audit metrics
    if batch:
        batch.committed_records += 1
        if batch.quarantined_records > 0:
            batch.quarantined_records -= 1
        batch.total_gross_value += txn.amount

    db.commit()
    return {
        "success": True,
        "message": f"Quarantine record {quarantine_id} successfully reprocessed and committed.",
        "transaction_id": txn.transaction_id,
        "reprocessing_attempts": rec.reprocessing_attempts,
    }


def reprocess_batch_quarantine(db: Session, batch_id: str) -> Dict[str, Any]:
    """Retries all pending quarantined records for a given batch."""
    pending_records = (
        db.query(ETLQuarantineRecord)
        .filter(
            ETLQuarantineRecord.batch_id == batch_id,
            ETLQuarantineRecord.resolution_status == "PENDING",
        )
        .all()
    )

    results = {
        "batch_id": batch_id,
        "total_attempted": len(pending_records),
        "reprocessed_successfully": 0,
        "still_quarantined": 0,
        "details": [],
    }

    for rec in pending_records:
        res = reprocess_quarantine_record(db, rec.quarantine_id)
        if res.get("success"):
            results["reprocessed_successfully"] += 1
        else:
            results["still_quarantined"] += 1
        results["details"].append({
            "quarantine_id": rec.quarantine_id,
            "row_number": rec.row_number,
            "success": res.get("success", False),
            "message": res.get("message", ""),
        })

    return results

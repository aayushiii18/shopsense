"""
routes/etl_routes.py — FastAPI REST endpoints for ETL ingestion, quarantine triage, reconciliation, and data mart operations.

Endpoints:
  POST /etl/batches/upload              Upload CSV file for chunked batch ingestion (Loopback-Guarded)
  GET  /etl/batches                     List paginated ingestion batches
  GET  /etl/batches/{batch_id}          Retrieve batch status and counters
  GET  /etl/batches/{batch_id}/records  List staged records for a batch
  GET  /etl/batches/{batch_id}/reconciliation  Batch reconciliation report
  GET  /etl/quarantine                  List quarantined records with status/category filters
  GET  /etl/quarantine/{record_id}      Get single quarantine record detail
  POST /etl/quarantine/{record_id}/reprocess  Reprocess single quarantine record (Loopback-Guarded)
  POST /etl/batches/{batch_id}/reprocess  Reprocess pending quarantine records for batch (Loopback-Guarded)
  POST /etl/marts/daily-sales/refresh   Trigger daily sales mart refresh / rebuild (Loopback-Guarded)
  GET  /etl/marts/daily-sales           Query aggregated daily sales mart
  GET  /etl/quality-report              Platform-wide reconciliation & data quality benchmarks
"""

import io
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.dependencies import require_admin
from app.schemas.etl_schema import (
    ETLBatchResponse,
    ETLBatchListResponse,
    ETLStagingRecordResponse,
    ETLStagingListResponse,
    ETLQuarantineRecordResponse,
    ETLQuarantineListResponse,
    QuarantineReprocessRequest,
    DailySalesMartRecordResponse,
    DailySalesMartQueryResponse,
    DailySalesMartRefreshRequest,
)
from app.services import etl as etl_service

router = APIRouter(prefix="/etl", tags=["ETL & Data Warehouse"])


# ── 1. Batch Upload & Ingestion ───────────────────────────────────────────────
@router.post(
    "/batches/upload",
    response_model=ETLBatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload CSV for bulk ingestion (Loopback-Guarded)",
    dependencies=[Depends(require_admin)],
)
async def upload_csv_batch(
    file: UploadFile = File(...),
    source_system: str = Form("CSV_INGEST"),
    chunk_size: int = Form(1000),
    sync_inventory: bool = Form(False),
    db: Session = Depends(get_db),
):
    """
    Receives and processes a bulk transaction CSV file in streaming chunks.
    Stages records, enforces row-level validation, applies database-level deduplication,
    isolates invalid records in quarantine, and snapshots commission tiers.
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only CSV files (.csv) are accepted for bulk ingestion.",
        )

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # Create batch record
    batch = etl_service.create_batch(
        db=db,
        filename=file.filename,
        file_bytes=file_bytes,
        source_system=source_system,
    )

    # Process batch in chunks
    file_stream = io.BytesIO(file_bytes)
    try:
        res = etl_service.process_csv_batch(
            db=db,
            batch_id=batch.batch_id,
            file_stream=file_stream,
            chunk_size=chunk_size,
            sync_inventory=sync_inventory,
            refresh_marts=True,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch processing error: {str(e)}",
        )

    # Reload batch record
    db.refresh(batch)
    return batch.to_dict()


# ── 2. Batch Inquiries & Auditing ─────────────────────────────────────────────
@router.get(
    "/batches",
    response_model=ETLBatchListResponse,
    summary="List paginated ingestion batches",
)
def list_batches_endpoint(
    status_filter: Optional[str] = Query(None, alias="status"),
    source_system: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Lists recent ETL batch runs and their processing states."""
    batches, total = etl_service.list_batches(
        db=db,
        status=status_filter,
        source_system=source_system,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "batches": batches,
    }


@router.get(
    "/batches/{batch_id}",
    response_model=ETLBatchResponse,
    summary="Get ETL batch detail",
)
def get_batch_endpoint(batch_id: str, db: Session = Depends(get_db)):
    """Retrieves status, counters, and error summaries for a specific batch."""
    batch = etl_service.get_batch(db, batch_id)
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Batch {batch_id} not found.")
    return batch.to_dict()


@router.get(
    "/batches/{batch_id}/records",
    response_model=ETLStagingListResponse,
    summary="List staged records for batch",
)
def get_batch_records_endpoint(
    batch_id: str,
    record_status: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieves buffered raw/staged records for a batch."""
    batch = etl_service.get_batch(db, batch_id)
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Batch {batch_id} not found.")

    records, total = etl_service.list_batch_staging_records(
        db=db,
        batch_id=batch_id,
        status=record_status,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "records": records,
    }


@router.get(
    "/batches/{batch_id}/reconciliation",
    summary="Get batch reconciliation report",
)
def get_batch_reconciliation_endpoint(batch_id: str, db: Session = Depends(get_db)):
    """Computes and returns the structured reconciliation audit for a batch."""
    report = etl_service.reconcile_batch(db, batch_id)
    if "error" in report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=report["error"])
    return report


# ── 3. Quarantine Management ──────────────────────────────────────────────────
@router.get(
    "/quarantine",
    response_model=ETLQuarantineListResponse,
    summary="List quarantined records",
)
def list_quarantine_endpoint(
    batch_id: Optional[str] = None,
    resolution_status: Optional[str] = None,
    error_category: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieves records isolated in quarantine with validation failure reasons."""
    records, total = etl_service.list_quarantine_records(
        db=db,
        batch_id=batch_id,
        resolution_status=resolution_status,
        error_category=error_category,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "records": records,
    }


@router.get(
    "/quarantine/{record_id}",
    response_model=ETLQuarantineRecordResponse,
    summary="Get single quarantine record",
)
def get_quarantine_endpoint(record_id: int, db: Session = Depends(get_db)):
    """Retrieves details of a quarantined record."""
    rec = etl_service.get_quarantine_record(db, record_id)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quarantine record {record_id} not found.",
        )
    return rec.to_dict()


@router.post(
    "/quarantine/{record_id}/reprocess",
    summary="Reprocess single quarantine record (Loopback-Guarded)",
    dependencies=[Depends(require_admin)],
)
def reprocess_quarantine_endpoint(
    record_id: int,
    payload: Optional[QuarantineReprocessRequest] = None,
    db: Session = Depends(get_db),
):
    """
    Submits corrections and attempts to re-validate and commit a quarantined record.
    """
    corrected_data = payload.corrected_data if payload else None
    result = etl_service.reprocess_quarantine_record(
        db=db,
        quarantine_id=record_id,
        corrected_data=corrected_data,
    )
    if not result.get("success") and "not found" in result.get("message", "").lower():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
    return result


@router.post(
    "/batches/{batch_id}/reprocess",
    summary="Reprocess all pending quarantine records for batch (Loopback-Guarded)",
    dependencies=[Depends(require_admin)],
)
def reprocess_batch_quarantine_endpoint(batch_id: str, db: Session = Depends(get_db)):
    """Retries all pending quarantined records for an entire batch."""
    batch = etl_service.get_batch(db, batch_id)
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Batch {batch_id} not found.")

    return etl_service.reprocess_batch_quarantine(db, batch_id)


# ── 4. Daily Sales Mart & Warehouse ───────────────────────────────────────────
@router.post(
    "/marts/daily-sales/refresh",
    summary="Refresh Daily Sales Mart (Loopback-Guarded)",
    dependencies=[Depends(require_admin)],
)
def refresh_daily_mart_endpoint(
    payload: Optional[DailySalesMartRefreshRequest] = None,
    db: Session = Depends(get_db),
):
    """
    Triggers an idempotent aggregation refresh of the Daily Sales Mart.
    Supports bounded date windows or complete historical rebuilds.
    """
    start_d = None
    end_d = None
    full_rebuild = False

    if payload:
        full_rebuild = payload.full_rebuild
        if payload.start_date:
            try:
                start_d = datetime.strptime(payload.start_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD.")
        if payload.end_date:
            try:
                end_d = datetime.strptime(payload.end_date, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD.")

    return etl_service.refresh_daily_sales_mart(
        db=db,
        start_date=start_d,
        end_date=end_d,
        full_rebuild=full_rebuild,
    )


@router.get(
    "/marts/daily-sales",
    response_model=DailySalesMartQueryResponse,
    summary="Query Daily Sales Mart",
)
def query_daily_mart_endpoint(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    vendor_id: Optional[int] = None,
    product_id: Optional[int] = None,
    category: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Queries aggregated dimensional sales data by date, product, vendor, and category."""
    start_d = None
    end_d = None
    if start_date:
        try:
            start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD.")
    if end_date:
        try:
            end_d = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD.")

    records, total, summary = etl_service.query_daily_sales_mart(
        db=db,
        start_date=start_d,
        end_date=end_d,
        vendor_id=vendor_id,
        product_id=product_id,
        category=category,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "summary": summary,
        "records": records,
    }


# ── 5. Platform Data Quality & Reconciliation ─────────────────────────────────
@router.get(
    "/quality-report",
    summary="Platform data quality & reconciliation benchmarks",
)
def get_quality_report_endpoint(db: Session = Depends(get_db)):
    """Computes system-wide data quality score, reconciliation benchmarks, and catalog health."""
    return etl_service.get_platform_data_quality_report(db)

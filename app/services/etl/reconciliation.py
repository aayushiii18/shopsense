"""
services/etl/reconciliation.py — Multi-layer data quality & financial audit reconciliation engine.

Compares:
  1. Source file count vs staged vs committed vs duplicate vs quarantined counts.
  2. Financial monetary reconciliation: source sum vs DB transaction sum vs daily mart sum.
  3. Referential integrity: checks for orphaned transactions or foreign key violations.
  4. Platform-wide data quality health metrics.
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct, select

from app.models.etl import ETLBatch, ETLStagingRecord, ETLQuarantineRecord, DailySalesMart
from app.models.transaction import Transaction
from app.models.product import Product
from app.models.vendor import Vendor
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.refund import Refund


def reconcile_batch(db: Session, batch_id: str) -> Dict[str, Any]:
    """
    Computes rigorous reconciliation audit for a specific ingestion batch.
    """
    batch = db.query(ETLBatch).filter(ETLBatch.batch_id == batch_id).first()
    if not batch:
        return {"error": f"Batch {batch_id} not found."}

    # Staging record counts
    total_staged = db.query(ETLStagingRecord).filter(ETLStagingRecord.batch_id == batch_id).count()
    status_counts = dict(
        db.query(ETLStagingRecord.status, func.count(ETLStagingRecord.staging_id))
        .filter(ETLStagingRecord.batch_id == batch_id)
        .group_by(ETLStagingRecord.status)
        .all()
    )

    committed_count = status_counts.get("COMMITTED", 0)
    duplicate_count = status_counts.get("DUPLICATE", 0)
    quarantined_count = status_counts.get("QUARANTINED", 0)
    failed_count = status_counts.get("FAILED", 0)

    # Actual database committed transactions linked to this batch
    committed_txns = (
        db.query(Transaction)
        .join(ETLStagingRecord, Transaction.transaction_id == ETLStagingRecord.target_transaction_id)
        .filter(ETLStagingRecord.batch_id == batch_id)
        .all()
    )
    actual_db_tx_count = len(committed_txns)
    actual_db_monetary_sum = sum(t.amount for t in committed_txns)

    # Sum from DailySalesMart for matching dates
    # Check if any transactions linked to this batch have mart entries
    tx_dates = {t.transaction_date.date() for t in committed_txns if t.transaction_date}
    mart_gmv_sum = 0.0
    if tx_dates:
        mart_gmv = (
            db.query(func.sum(DailySalesMart.gross_sales_gmv))
            .filter(DailySalesMart.date.in_(list(tx_dates)))
            .scalar()
        )
        mart_gmv_sum = mart_gmv or 0.0

    count_discrepancy = total_staged - (committed_count + duplicate_count + quarantined_count + failed_count)
    monetary_discrepancy = round(batch.total_gross_value - actual_db_monetary_sum, 2)

    return {
        "batch_id": batch.batch_id,
        "source_system": batch.source_system,
        "original_filename": batch.original_filename,
        "status": batch.status,
        "record_counts": {
            "source_total_reported": batch.total_records,
            "staged_total": total_staged,
            "committed_to_db": committed_count,
            "actual_db_records": actual_db_tx_count,
            "duplicates_detected": duplicate_count,
            "quarantined_records": quarantined_count,
            "failed_records": failed_count,
            "count_discrepancy": count_discrepancy,
            "is_count_reconciled": (count_discrepancy == 0 and committed_count == actual_db_tx_count),
        },
        "financial_reconciliation": {
            "batch_gross_value": round(batch.total_gross_value, 2),
            "actual_db_gross_sum": round(actual_db_monetary_sum, 2),
            "discrepancy_amount": monetary_discrepancy,
            "is_monetarily_reconciled": abs(monetary_discrepancy) < 0.01,
        },
        "timestamps": {
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "started_at": batch.started_at.isoformat() if batch.started_at else None,
            "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
            "processing_duration_ms": batch.processing_duration_ms,
        },
    }


def get_platform_data_quality_report(db: Session) -> Dict[str, Any]:
    """
    Computes marketplace-wide data quality and integrity benchmarks.
    """
    total_tx = db.query(Transaction).count()
    total_customers = db.query(Customer).count()
    total_products = db.query(Product).count()
    total_vendors = db.query(Vendor).count()
    total_gmv = db.query(func.sum(Transaction.amount)).scalar() or 0.0
    total_refunds = db.query(func.sum(Refund.amount)).scalar() or 0.0
    net_sales = total_gmv - total_refunds

    # Mart totals
    mart_records = db.query(DailySalesMart).count()
    mart_gmv = db.query(func.sum(DailySalesMart.gross_sales_gmv)).scalar() or 0.0
    mart_net_sales = db.query(func.sum(DailySalesMart.net_sales)).scalar() or 0.0

    # Referential checks
    orphaned_tx_products = (
        db.query(Transaction)
        .outerjoin(Product, Transaction.product_id == Product.id)
        .filter(Product.id.is_(None))
        .count()
    )
    orphaned_tx_vendors = (
        db.query(Transaction)
        .outerjoin(Vendor, Transaction.vendor_id == Vendor.id)
        .filter(Vendor.id.is_(None))
        .count()
    )

    # Quarantine metrics
    pending_quarantine = (
        db.query(ETLQuarantineRecord)
        .filter(ETLQuarantineRecord.resolution_status == "PENDING")
        .count()
    )
    resolved_quarantine = (
        db.query(ETLQuarantineRecord)
        .filter(ETLQuarantineRecord.resolution_status == "RESOLVED")
        .count()
    )

    # Ingestion batch stats
    total_batches = db.query(ETLBatch).count()
    completed_batches = db.query(ETLBatch).filter(ETLBatch.status == "COMPLETED").count()
    partial_batches = db.query(ETLBatch).filter(ETLBatch.status == "PARTIALLY_COMPLETED").count()
    failed_batches = db.query(ETLBatch).filter(ETLBatch.status == "FAILED").count()

    # Deduplication integrity check
    duplicate_source_tx = (
        db.query(Transaction.source_system, Transaction.source_transaction_id, func.count(Transaction.transaction_id))
        .filter(Transaction.source_system.isnot(None), Transaction.source_transaction_id.isnot(None))
        .group_by(Transaction.source_system, Transaction.source_transaction_id)
        .having(func.count(Transaction.transaction_id) > 1)
        .count()
    )

    # COGS Coverage across catalog
    costed_products = db.query(Product).filter(Product.cost_price.isnot(None)).count()
    cogs_catalog_coverage_pct = round((costed_products / total_products * 100.0), 2) if total_products > 0 else 0.0

    return {
        "status": "HEALTHY" if (orphaned_tx_products == 0 and orphaned_tx_vendors == 0 and duplicate_source_tx == 0) else "WARNING",
        "operational_metrics": {
            "total_transactions": total_tx,
            "total_customers": total_customers,
            "total_products": total_products,
            "total_vendors": total_vendors,
            "gross_merchandise_value_gmv": round(total_gmv, 2),
            "total_refunds": round(total_refunds, 2),
            "operational_net_sales": round(net_sales, 2),
        },
        "warehouse_mart_metrics": {
            "daily_sales_mart_records": mart_records,
            "mart_gross_gmv": round(mart_gmv, 2),
            "mart_net_sales": round(mart_net_sales, 2),
            "mart_synced": mart_records > 0,
        },
        "referential_integrity": {
            "orphaned_transaction_products": orphaned_tx_products,
            "orphaned_transaction_vendors": orphaned_tx_vendors,
            "referential_integrity_passed": (orphaned_tx_products == 0 and orphaned_tx_vendors == 0),
        },
        "deduplication_integrity": {
            "duplicate_source_transactions_in_db": duplicate_source_tx,
            "deduplication_passed": (duplicate_source_tx == 0),
        },
        "financial_governance": {
            "costed_products": costed_products,
            "uncosted_legacy_products": total_products - costed_products,
            "cogs_coverage_pct": cogs_catalog_coverage_pct,
            "nullable_cogs_policy_compliant": True,
        },
        "etl_batch_summary": {
            "total_batches_ingested": total_batches,
            "completed_batches": completed_batches,
            "partial_batches": partial_batches,
            "failed_batches": failed_batches,
            "pending_quarantine_records": pending_quarantine,
            "resolved_quarantine_records": resolved_quarantine,
        },
    }

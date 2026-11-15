"""
tests/test_stage6_etl.py — Comprehensive Test Suite for Stage 6: Structured ETL, Bulk Data Ingestion & Data Warehouse.

Covers all 20 required testing scenarios:
  1. Valid CSV ingestion.
  2. Invalid file handling (empty file, non-csv extension).
  3. Missing required columns.
  4. Malformed data (bad dates, non-numeric prices/quantities).
  5. Invalid foreign keys (non-existent product_id, vendor_id, customer_id).
  6. Duplicate records within one batch (in-batch duplicate collision).
  7. Duplicate records across batches (cross-batch idempotency).
  8. Database-level idempotency (unique constraint on source_system + source_transaction_id).
  9. Safe batch reprocessing without data corruption.
  10. Quarantine creation (preservation of raw payload, error categorization).
  11. Quarantine correction and reprocessing.
  12. Partial batch failures (status = PARTIALLY_COMPLETED).
  13. Batch audit counters accuracy (staged, committed, duplicate, quarantined, failed, gross value).
  14. Financial reconciliation (batch reported gross value == DB transaction sum).
  15. Inventory synchronization and movement tracking.
  16. Daily sales mart aggregation (date x product x vendor grain, GMV, Net Sales, Nullable COGS).
  17. Repeated daily mart refresh without duplicate aggregates (idempotent upsert).
  18. Scheduled job overlap protection and concurrency locks.
  19. FastAPI ETL endpoints validation and status codes.
  20. Regression of Stages 1–5 invariants and models.
"""

import io
import json
import pytest
from datetime import datetime, date, timedelta

from app.models.vendor import Vendor
from app.models.product import Product
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.models.inventory import Inventory
from app.models.stock_movement import StockMovement
from app.models.refund import Refund
from app.models.etl import ETLBatch, ETLStagingRecord, ETLQuarantineRecord, DailySalesMart

from app.services import etl as etl_service
from app.scheduler import run_scheduled_daily_mart_refresh, _mart_refresh_running


def _seed_base_catalog(db):
    """Seeds baseline vendor, product, inventory, and customer for ETL testing."""
    v1 = Vendor(
        id=1,
        name="Apex Supplies",
        email="apex@supplies.com",
        phone="+1-800-555-0100",
        commission_tier="TIER_STANDARD",
        commission_rate=0.12,
        status="LEGACY_ACTIVE",
    )
    v2 = Vendor(
        id=2,
        name="Beacon Logistics",
        email="beacon@logistics.com",
        phone="+1-800-555-0200",
        commission_tier="TIER_PREFERRED",
        commission_rate=0.10,
        status="LEGACY_ACTIVE",
    )
    p1 = Product(
        id=1,
        name="Wireless Keyboard",
        price=50.0,
        cost_price=25.0,  # cost-verified item
        category="Electronics",
        vendor_id=1,
    )
    p2 = Product(
        id=2,
        name="Legacy Desk Mat",
        price=20.0,
        cost_price=None,  # uncosted legacy item (preserves Nullable COGS rule)
        category="Office",
        vendor_id=2,
    )
    inv1 = Inventory(product_id=1, current_stock=100, warehouse="Main Warehouse", reorder_level=10)
    inv2 = Inventory(product_id=2, current_stock=50, warehouse="North Warehouse", reorder_level=5)
    c1 = Customer(
        customer_id=1,
        name="Alice Retail",
        email="alice@retail.com",
        city="New York",
    )
    db.add_all([v1, v2, p1, p2, inv1, inv2, c1])
    db.commit()
    return v1, v2, p1, p2, inv1, inv2, c1


# ── Scenario 1: Valid CSV Ingestion ───────────────────────────────────────────
def test_valid_csv_ingestion(db_session):
    """Scenario 1: Valid CSV ingests cleanly, creating transactions and batch summary."""
    _seed_base_catalog(db_session)
    csv_content = (
        "source_transaction_id,product_id,vendor_id,customer_id,quantity,unit_price,discount_amount,transaction_date\n"
        "TX101,1,1,1,2,50.0,5.0,2024-05-10 14:00:00\n"
        "TX102,2,2,1,1,20.0,0.0,2024-05-10 15:30:00\n"
    ).encode("utf-8")

    batch = etl_service.create_batch(db_session, "orders_valid.csv", csv_content)
    result = etl_service.process_csv_batch(
        db_session, batch.batch_id, io.BytesIO(csv_content), refresh_marts=True
    )

    assert result["status"] == "COMPLETED"
    assert result["total_records"] == 2
    assert result["committed_records"] == 2
    assert result["quarantined_records"] == 0
    assert result["duplicate_records"] == 0
    assert result["total_gross_value"] == 120.0  # (2*50) + (1*20)

    # Check database transactions
    txns = db_session.query(Transaction).filter(Transaction.source_system == "CSV_INGEST").all()
    assert len(txns) == 2
    tx_map = {t.source_transaction_id: t for t in txns}
    assert tx_map["TX101"].amount == 100.0
    assert tx_map["TX101"].discount_amount == 5.0
    assert tx_map["TX101"].effective_commission_rate == 0.12  # Snapshotted from vendor 1


# ── Scenario 2: Invalid File Handling ─────────────────────────────────────────
def test_invalid_file_handling(client, db_session):
    """Scenario 2: Rejects non-CSV extensions and empty files with HTTP 400."""
    _seed_base_catalog(db_session)

    # 1. Non-CSV extension
    res_bad_ext = client.post(
        "/etl/batches/upload",
        files={"file": ("transactions.pdf", b"%PDF-1.4 binary content", "application/pdf")},
    )
    assert res_bad_ext.status_code == 400
    assert "Only CSV files" in res_bad_ext.json()["detail"]

    # 2. Empty CSV file
    res_empty = client.post(
        "/etl/batches/upload",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert res_empty.status_code == 400
    assert "Uploaded file is empty" in res_empty.json()["detail"]


# ── Scenario 3: Missing Required Columns ──────────────────────────────────────
def test_missing_required_columns(db_session):
    """Scenario 3: CSV missing mandatory columns quarantines rows with VALIDATION_ERROR."""
    _seed_base_catalog(db_session)
    csv_missing = (
        "source_transaction_id,customer_id\n"
        "TX201,1\n"
    ).encode("utf-8")

    batch = etl_service.create_batch(db_session, "missing_cols.csv", csv_missing)
    res = etl_service.process_csv_batch(db_session, batch.batch_id, io.BytesIO(csv_missing))

    assert res["status"] == "FAILED"
    assert res["committed_records"] == 0
    assert res["quarantined_records"] == 1

    quarantine_rec = db_session.query(ETLQuarantineRecord).filter(ETLQuarantineRecord.batch_id == batch.batch_id).first()
    assert quarantine_rec is not None
    assert quarantine_rec.error_category == "VALIDATION_ERROR"
    assert "Missing required field" in quarantine_rec.error_details


# ── Scenario 4: Malformed Data ────────────────────────────────────────────────
def test_malformed_data(db_session):
    """Scenario 4: Malformed numbers and corrupted dates are safely quarantined."""
    _seed_base_catalog(db_session)
    csv_malformed = (
        "source_transaction_id,product_id,vendor_id,quantity,unit_price,transaction_date\n"
        "TX301,1,1,INVALID_QTY,50.0,2024-05-10\n"
        "TX302,1,1,2,NOT_A_PRICE,2024-05-10\n"
        "TX303,1,1,2,50.0,BAD_DATE_FORMAT_STRING\n"
    ).encode("utf-8")

    batch = etl_service.create_batch(db_session, "malformed.csv", csv_malformed)
    res = etl_service.process_csv_batch(db_session, batch.batch_id, io.BytesIO(csv_malformed))

    assert res["status"] == "FAILED"
    assert res["committed_records"] == 0
    assert res["quarantined_records"] == 3

    categories = {q.error_category for q in db_session.query(ETLQuarantineRecord).filter(ETLQuarantineRecord.batch_id == batch.batch_id).all()}
    assert "INVALID_DATA_TYPE" in categories or "MALFORMED_ROW" in categories


# ── Scenario 5: Invalid Foreign Keys ──────────────────────────────────────────
def test_invalid_foreign_keys(db_session):
    """Scenario 5: Non-existent product_id or vendor_id triggers MISSING_FOREIGN_KEY quarantine."""
    _seed_base_catalog(db_session)
    csv_fk = (
        "source_transaction_id,product_id,vendor_id,quantity,unit_price\n"
        "TX401,999,1,2,50.0\n"   # Non-existent product 999
        "TX402,1,888,2,50.0\n"   # Non-existent vendor 888
    ).encode("utf-8")

    batch = etl_service.create_batch(db_session, "invalid_fk.csv", csv_fk)
    res = etl_service.process_csv_batch(db_session, batch.batch_id, io.BytesIO(csv_fk))

    assert res["status"] == "FAILED"
    assert res["committed_records"] == 0
    assert res["quarantined_records"] == 2

    q_records = db_session.query(ETLQuarantineRecord).filter(ETLQuarantineRecord.batch_id == batch.batch_id).all()
    for q in q_records:
        assert q.error_category == "MISSING_FOREIGN_KEY"


# ── Scenario 6: In-Batch Duplicate Collisions ─────────────────────────────────
def test_duplicate_records_within_one_batch(db_session):
    """Scenario 6: Same source_transaction_id appearing multiple times in one file is deduplicated."""
    _seed_base_catalog(db_session)
    csv_in_dup = (
        "source_transaction_id,product_id,vendor_id,quantity,unit_price\n"
        "TX501,1,1,2,50.0\n"
        "TX501,1,1,3,50.0\n"  # Duplicate source ID in same upload
    ).encode("utf-8")

    batch = etl_service.create_batch(db_session, "in_batch_dup.csv", csv_in_dup)
    res = etl_service.process_csv_batch(db_session, batch.batch_id, io.BytesIO(csv_in_dup))

    assert res["status"] == "PARTIALLY_COMPLETED"
    assert res["total_records"] == 2
    assert res["committed_records"] == 1
    assert res["duplicate_records"] == 1

    # Verify only 1 committed row in DB
    txns = db_session.query(Transaction).filter(Transaction.source_transaction_id == "TX501").all()
    assert len(txns) == 1
    assert txns[0].quantity == 2


# ── Scenario 7: Cross-Batch Duplicate Collisions ──────────────────────────────
def test_duplicate_records_across_batches(db_session):
    """Scenario 7: Re-uploading a previously committed transaction is detected as cross-batch duplicate."""
    _seed_base_catalog(db_session)
    csv_1 = "source_transaction_id,product_id,vendor_id,quantity,unit_price\nTX601,1,1,2,50.0\n".encode("utf-8")
    batch_1 = etl_service.create_batch(db_session, "batch_1.csv", csv_1)
    res_1 = etl_service.process_csv_batch(db_session, batch_1.batch_id, io.BytesIO(csv_1))
    assert res_1["committed_records"] == 1

    # Second batch with same external source ID
    csv_2 = "source_transaction_id,product_id,vendor_id,quantity,unit_price\nTX601,1,1,2,50.0\n".encode("utf-8")
    batch_2 = etl_service.create_batch(db_session, "batch_2.csv", csv_2)
    res_2 = etl_service.process_csv_batch(db_session, batch_2.batch_id, io.BytesIO(csv_2))

    assert res_2["status"] == "PARTIALLY_COMPLETED" or res_2["status"] == "FAILED"
    assert res_2["committed_records"] == 0
    assert res_2["duplicate_records"] == 1

    txns = db_session.query(Transaction).filter(Transaction.source_transaction_id == "TX601").all()
    assert len(txns) == 1  # No duplicate created in transactions table


# ── Scenario 8: Database-Level Idempotency ───────────────────────────────────
def test_database_level_idempotency(db_session):
    """Scenario 8: Enforces database unique constraint on (source_system, source_transaction_id)."""
    _seed_base_catalog(db_session)
    t1 = Transaction(
        product_id=1,
        vendor_id=1,
        quantity=2,
        unit_price=50.0,
        amount=100.0,
        source_system="ERP_SYSTEM",
        source_transaction_id="ERP-9999",
        transaction_date=datetime.utcnow(),
    )
    db_session.add(t1)
    db_session.commit()

    # Attempt to insert identical tuple at SQL/ORM level
    t2 = Transaction(
        product_id=1,
        vendor_id=1,
        quantity=3,
        unit_price=50.0,
        amount=150.0,
        source_system="ERP_SYSTEM",
        source_transaction_id="ERP-9999",
        transaction_date=datetime.utcnow(),
    )
    db_session.add(t2)
    with pytest.raises(Exception):
        db_session.commit()
    db_session.rollback()


# ── Scenario 9: Safe Batch Reprocessing ───────────────────────────────────────
def test_safe_batch_reprocessing(db_session):
    """Scenario 9: Re-processing an existing file does not inflate records or distort totals."""
    _seed_base_catalog(db_session)
    csv_content = (
        "source_transaction_id,product_id,vendor_id,quantity,unit_price\n"
        "TX701,1,1,1,50.0\n"
        "TX702,2,2,2,20.0\n"
    ).encode("utf-8")

    batch_1 = etl_service.create_batch(db_session, "orders_safe.csv", csv_content)
    etl_service.process_csv_batch(db_session, batch_1.batch_id, io.BytesIO(csv_content))
    total_before = db_session.query(Transaction).count()

    # Re-upload same file
    batch_2 = etl_service.create_batch(db_session, "orders_safe_retry.csv", csv_content)
    res_2 = etl_service.process_csv_batch(db_session, batch_2.batch_id, io.BytesIO(csv_content))

    assert res_2["duplicate_records"] == 2
    assert res_2["committed_records"] == 0
    total_after = db_session.query(Transaction).count()
    assert total_after == total_before


# ── Scenario 10: Quarantine Creation ─────────────────────────────────────────
def test_quarantine_creation(db_session):
    """Scenario 10: Rejected rows create persistent quarantine records preserving raw inputs."""
    _seed_base_catalog(db_session)
    csv_bad = "source_transaction_id,product_id,vendor_id,quantity,unit_price\nTX801,999,1,5,50.0\n".encode("utf-8")

    batch = etl_service.create_batch(db_session, "quarantine_test.csv", csv_bad)
    etl_service.process_csv_batch(db_session, batch.batch_id, io.BytesIO(csv_bad))

    q_records, count = etl_service.list_quarantine_records(db_session, batch_id=batch.batch_id)
    assert count == 1
    q = q_records[0]
    assert q["source_transaction_id"] == "TX801"
    assert q["resolution_status"] == "PENDING"
    assert q["reprocessing_attempts"] == 0
    assert "999" in q["raw_data"]


# ── Scenario 11: Quarantine Correction and Reprocessing ───────────────────────
def test_quarantine_correction_and_reprocessing(db_session):
    """Scenario 11: Supplying corrections to a quarantined record validates and commits it."""
    _seed_base_catalog(db_session)
    csv_bad = "source_transaction_id,product_id,vendor_id,quantity,unit_price\nTX901,999,1,2,50.0\n".encode("utf-8")

    batch = etl_service.create_batch(db_session, "triage_test.csv", csv_bad)
    etl_service.process_csv_batch(db_session, batch.batch_id, io.BytesIO(csv_bad))

    q_rec = db_session.query(ETLQuarantineRecord).filter(ETLQuarantineRecord.batch_id == batch.batch_id).first()
    assert q_rec.resolution_status == "PENDING"

    # Correct product_id to 1 (which exists)
    correction = {"product_id": 1}
    rep_res = etl_service.reprocess_quarantine_record(db_session, q_rec.quarantine_id, corrected_data=correction)

    assert rep_res["success"] is True
    assert "successfully reprocessed" in rep_res["message"]

    db_session.refresh(q_rec)
    assert q_rec.resolution_status == "RESOLVED"
    assert q_rec.reprocessing_attempts == 1

    # Verify committed transaction
    txn = db_session.query(Transaction).filter(Transaction.source_transaction_id == "TX901").first()
    assert txn is not None
    assert txn.product_id == 1
    assert txn.amount == 100.0


# ── Scenario 12: Partial Batch Failures ───────────────────────────────────────
def test_partial_batch_failures(db_session):
    """Scenario 12: Batch with mixed valid and invalid rows completes with PARTIALLY_COMPLETED status."""
    _seed_base_catalog(db_session)
    csv_mixed = (
        "source_transaction_id,product_id,vendor_id,quantity,unit_price\n"
        "TX1001,1,1,2,50.0\n"       # Valid
        "TX1002,999,1,1,20.0\n"     # Invalid product
        "TX1003,2,2,-5,20.0\n"      # Invalid negative quantity
    ).encode("utf-8")

    batch = etl_service.create_batch(db_session, "mixed.csv", csv_mixed)
    res = etl_service.process_csv_batch(db_session, batch.batch_id, io.BytesIO(csv_mixed))

    assert res["status"] == "PARTIALLY_COMPLETED"
    assert res["total_records"] == 3
    assert res["committed_records"] == 1
    assert res["quarantined_records"] == 2


# ── Scenario 13: Batch Audit Counters ─────────────────────────────────────────
def test_batch_audit_counters(db_session):
    """Scenario 13: Accurate tracking of staged, committed, duplicate, quarantined, and duration metrics."""
    _seed_base_catalog(db_session)
    csv_audit = (
        "source_transaction_id,product_id,vendor_id,quantity,unit_price\n"
        "TX1101,1,1,1,50.0\n"
        "TX1101,1,1,1,50.0\n"  # Duplicate
        "TX1102,999,1,1,50.0\n" # Quarantined
    ).encode("utf-8")

    batch = etl_service.create_batch(db_session, "audit_test.csv", csv_audit)
    res = etl_service.process_csv_batch(db_session, batch.batch_id, io.BytesIO(csv_audit))

    db_session.refresh(batch)
    assert batch.total_records == 3
    assert batch.staged_records == 3
    assert batch.committed_records == 1
    assert batch.duplicate_records == 1
    assert batch.quarantined_records == 1
    assert batch.processing_duration_ms > 0
    assert batch.total_gross_value == 50.0


# ── Scenario 14: Financial Reconciliation ─────────────────────────────────────
def test_financial_reconciliation(db_session):
    """Scenario 14: Batch reported gross value matches actual database transactions exactly."""
    _seed_base_catalog(db_session)
    csv_fin = (
        "source_transaction_id,product_id,vendor_id,quantity,unit_price\n"
        "TX1201,1,1,4,50.0\n"
        "TX1202,2,2,3,20.0\n"
    ).encode("utf-8")

    batch = etl_service.create_batch(db_session, "financial_test.csv", csv_fin)
    etl_service.process_csv_batch(db_session, batch.batch_id, io.BytesIO(csv_fin))

    recon = etl_service.reconcile_batch(db_session, batch.batch_id)
    fin = recon["financial_reconciliation"]

    assert fin["is_monetarily_reconciled"] is True
    assert fin["batch_gross_value"] == 260.0  # (4*50) + (3*20)
    assert fin["actual_db_gross_sum"] == 260.0
    assert fin["discrepancy_amount"] == 0.0


# ── Scenario 15: Inventory Synchronization ────────────────────────────────────
def test_inventory_synchronization(db_session):
    """Scenario 15: When sync_inventory is enabled, stock is decremented and StockMovement logged."""
    _seed_base_catalog(db_session)
    inv_before = db_session.query(Inventory).filter(Inventory.product_id == 1).first().current_stock
    assert inv_before == 100

    csv_inv = "source_transaction_id,product_id,vendor_id,quantity,unit_price\nTX1301,1,1,10,50.0\n".encode("utf-8")
    batch = etl_service.create_batch(db_session, "inv_sync.csv", csv_inv)
    etl_service.process_csv_batch(db_session, batch.batch_id, io.BytesIO(csv_inv), sync_inventory=True)

    inv_after = db_session.query(Inventory).filter(Inventory.product_id == 1).first().current_stock
    assert inv_after == 90  # 100 - 10

    # StockMovement record created
    mv = db_session.query(StockMovement).filter(StockMovement.product_id == 1, StockMovement.movement_type == "SALE").first()
    assert mv is not None
    assert mv.quantity == -10


# ── Scenario 16: Daily Mart Aggregation ───────────────────────────────────────
def test_daily_mart_aggregation(db_session):
    """Scenario 16: Daily sales mart aggregates by (date, product, vendor) with Nullable COGS."""
    _seed_base_catalog(db_session)
    d1 = datetime(2024, 6, 15, 10, 0, 0)
    d2 = datetime(2024, 6, 15, 12, 0, 0)

    # Two transactions on product 1 (cost_price=25.0)
    t1 = Transaction(product_id=1, vendor_id=1, quantity=2, unit_price=50.0, amount=100.0, discount_amount=10.0, transaction_date=d1)
    t2 = Transaction(product_id=1, vendor_id=1, quantity=3, unit_price=50.0, amount=150.0, discount_amount=0.0, transaction_date=d2)

    # One transaction on product 2 (cost_price=None, legacy uncosted)
    t3 = Transaction(product_id=2, vendor_id=2, quantity=4, unit_price=20.0, amount=80.0, discount_amount=0.0, transaction_date=d1)

    db_session.add_all([t1, t2, t3])
    db_session.commit()

    res = etl_service.refresh_daily_sales_mart(db_session, full_rebuild=True)
    assert res["status"] == "SUCCESS"

    marts = db_session.query(DailySalesMart).filter(DailySalesMart.date == d1.date()).all()
    assert len(marts) == 2
    mart_map = {m.product_id: m for m in marts}

    # Product 1 (costed item)
    m1 = mart_map[1]
    assert m1.units_sold == 5  # 2 + 3
    assert m1.gross_sales_gmv == 250.0
    assert m1.discounts_total == 10.0
    assert m1.net_sales == 240.0
    assert m1.known_cogs == 125.0  # 5 * 25.0
    assert m1.reported_gross_profit == 115.0  # 240 - 125
    assert m1.cogs_coverage_pct == 100.0

    # Product 2 (uncosted legacy item)
    m2 = mart_map[2]
    assert m2.units_sold == 4
    assert m2.gross_sales_gmv == 80.0
    assert m2.known_cogs is None  # Preserves Nullable COGS rule!
    assert m2.reported_gross_profit is None
    assert m2.cogs_coverage_pct == 0.0


# ── Scenario 17: Repeated Daily Mart Refresh (Idempotence) ────────────────────
def test_repeated_daily_mart_refresh_idempotence(db_session):
    """Scenario 17: Consecutive mart refreshes do not duplicate records or inflate metrics."""
    _seed_base_catalog(db_session)
    d = datetime(2024, 7, 1, 10, 0, 0)
    t = Transaction(product_id=1, vendor_id=1, quantity=2, unit_price=50.0, amount=100.0, transaction_date=d)
    db_session.add(t)
    db_session.commit()

    etl_service.refresh_daily_sales_mart(db_session, full_rebuild=True)
    marts_1 = db_session.query(DailySalesMart).all()
    assert len(marts_1) == 1
    gmv_1 = marts_1[0].gross_sales_gmv

    # Second refresh without full rebuild (incremental upsert)
    etl_service.refresh_daily_sales_mart(db_session, full_rebuild=False)
    marts_2 = db_session.query(DailySalesMart).all()
    assert len(marts_2) == 1
    assert marts_2[0].gross_sales_gmv == gmv_1


# ── Scenario 18: Scheduled Job Overlap Protection ─────────────────────────────
def test_scheduled_job_overlap_protection(db_session):
    """Scenario 18: Prevents concurrent execution of Daily Sales Mart refresh using in-process lock."""
    _seed_base_catalog(db_session)

    # First run succeeds
    res_1 = run_scheduled_daily_mart_refresh(db=db_session, full_rebuild=False)
    assert res_1["status"] in ("SUCCESS", "SKIPPED")

    # Simulate active concurrent lock
    from app import scheduler
    scheduler._mart_refresh_running = True
    try:
        res_overlap = run_scheduled_daily_mart_refresh(db=db_session)
        assert res_overlap["status"] == "SKIPPED"
        assert "Overlapping run prevented" in res_overlap["message"]
    finally:
        scheduler._mart_refresh_running = False


# ── Scenario 19: API Endpoints Validation ─────────────────────────────────────
def test_api_endpoints_validation(client, db_session):
    """Scenario 19: Tests REST API routes for batch upload, listing, quarantine, and data quality."""
    _seed_base_catalog(db_session)

    # 1. Upload batch
    csv_bytes = "source_transaction_id,product_id,vendor_id,quantity,unit_price\nTXAPI1,1,1,2,50.0\n".encode("utf-8")
    resp_up = client.post(
        "/etl/batches/upload",
        files={"file": ("api_test.csv", csv_bytes, "text/csv")},
    )
    assert resp_up.status_code == 201
    batch_data = resp_up.json()
    batch_id = batch_data["batch_id"]

    # 2. Get batch detail
    resp_b = client.get(f"/etl/batches/{batch_id}")
    assert resp_b.status_code == 200
    assert resp_b.json()["batch_id"] == batch_id

    # 3. List batches
    resp_list = client.get("/etl/batches")
    assert resp_list.status_code == 200
    assert resp_list.json()["total"] >= 1

    # 4. Batch reconciliation endpoint
    resp_rec = client.get(f"/etl/batches/{batch_id}/reconciliation")
    assert resp_rec.status_code == 200
    assert resp_rec.json()["financial_reconciliation"]["is_monetarily_reconciled"] is True

    # 5. Platform data quality report
    resp_qual = client.get("/etl/quality-report")
    assert resp_qual.status_code == 200
    assert "referential_integrity" in resp_qual.json()


# ── Scenario 20: Regression of Stages 1–5 Invariants ──────────────────────────
def test_stages_1_to_5_regression(db_session):
    """Scenario 20: Validates that Stage 1-5 schemas, relations, and accounting rules remain intact."""
    _seed_base_catalog(db_session)

    # Verify Vendor Commission Tier & Nullable COGS
    v = db_session.query(Vendor).filter(Vendor.id == 1).first()
    assert v.commission_tier == "TIER_STANDARD"
    assert v.commission_rate == 0.12

    p = db_session.query(Product).filter(Product.id == 2).first()
    assert p.cost_price is None  # Legacy product cost price must remain strictly nullable

    # Verify Refund relationship
    t = Transaction(product_id=1, vendor_id=1, quantity=1, unit_price=50.0, amount=50.0)
    db_session.add(t)
    db_session.commit()

    ref = Refund(
        transaction_id=t.transaction_id,
        idempotency_key="REF-TEST-001",
        amount=50.0,
        status="COMPLETED",
        returned_quantity=1,
    )
    db_session.add(ref)
    db_session.commit()

    assert len(t.refunds) == 1
    assert t.refunds[0].amount == 50.0

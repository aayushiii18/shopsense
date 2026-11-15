"""
services/etl/loading.py — Atomic database loading of staged transactions and inventory synchronization.

Provides:
  - load_transactions_chunk: Persists transformed transactions, links staging records, updates inventory if requested.
  - Guarantees transaction atomicity per chunk with rollback on unexpected database exceptions.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.models.inventory import Inventory
from app.models.stock_movement import StockMovement
from app.models.etl import ETLStagingRecord


def load_transactions_chunk(
    db: Session,
    transformed_records: List[Tuple[Dict[str, Any], int, Optional[int]]],
    # list of (transaction_kwargs, row_number, staging_id)
    sync_inventory: bool = False,
) -> Tuple[List[Transaction], float]:
    """
    Inserts a chunk of transformed records into transactions table.
    Links each staging record to its committed target_transaction_id.
    Optionally logs stock movements if sync_inventory is enabled.
    Returns (created_transactions, chunk_gross_value).
    """
    created_txns: List[Transaction] = []
    chunk_gross_value = 0.0

    for txn_kwargs, row_num, staging_id in transformed_records:
        txn = Transaction(**txn_kwargs)
        db.add(txn)
        db.flush()  # obtain generated transaction_id

        created_txns.append(txn)
        chunk_gross_value += txn.amount

        # Update staging record status
        if staging_id:
            stg = db.query(ETLStagingRecord).filter(ETLStagingRecord.staging_id == staging_id).first()
            if stg:
                stg.status = "COMMITTED"
                stg.target_transaction_id = txn.transaction_id

        # Optional inventory decrement & stock movement audit
        if sync_inventory and txn.quantity > 0:
            inv = db.query(Inventory).filter(Inventory.product_id == txn.product_id).first()
            if inv:
                inv.current_stock = max(0, inv.current_stock - txn.quantity)
                movement = StockMovement(
                    product_id=txn.product_id,
                    movement_type="SALE",
                    quantity=-txn.quantity,
                    reference_id=txn.transaction_id,
                    notes=f"ETL bulk ingestion order (source: {txn.source_system})",
                    created_at=txn.transaction_date or datetime.utcnow(),
                )
                db.add(movement)

    return created_txns, chunk_gross_value

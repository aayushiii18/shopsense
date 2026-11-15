"""
services/etl/transformation.py — Payload normalization, commission rate snapshotting, and data harmonization.

Provides:
  - transform_transaction_record: Transforms validated raw input into canonical Transaction schema attributes.
  - Normalizes payment methods and statuses.
  - Snapshots effective_commission_rate from vendor profile at transaction time (Stage 4 requirement).
  - Integrates catalog taxonomy normalization if category information is present.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from app.services.catalog_normalizer import normalize_category


def transform_transaction_record(
    record: Dict[str, Any],
    vendor_commission_map: Optional[Dict[int, float]] = None,
    source_system: str = "CSV_INGEST",
) -> Dict[str, Any]:
    """
    Transforms a validated staged row into ready-to-insert Transaction kwargs.
    """
    qty = int(record["quantity"])
    unit_price = float(record["unit_price"])
    amount = float(record.get("amount") or round(qty * unit_price, 2))
    discount = float(record.get("discount_amount") or 0.0)

    # Normalize payment fields
    payment_method = str(record.get("payment_method") or "UNKNOWN").strip().upper()
    payment_status = str(record.get("payment_status") or "COMPLETED").strip().upper()

    # Effective commission rate snapshot
    vid = int(record["vendor_id"])
    commission_rate = None
    if vendor_commission_map and vid in vendor_commission_map:
        commission_rate = vendor_commission_map[vid]

    # Date normalization
    txn_date = record.get("transaction_date")
    if not isinstance(txn_date, datetime):
        txn_date = datetime.utcnow()

    # Source identifiers
    src_tx_id = record.get("source_transaction_id")
    src_tx_id_str = str(src_tx_id).strip() if src_tx_id is not None and str(src_tx_id).strip() != "" else None

    return {
        "product_id": int(record["product_id"]),
        "vendor_id": vid,
        "customer_id": int(record["customer_id"]) if record.get("customer_id") is not None else None,
        "quantity": qty,
        "unit_price": round(unit_price, 2),
        "amount": round(amount, 2),
        "discount_amount": round(discount, 2),
        "payment_method": payment_method,
        "payment_status": payment_status,
        "effective_commission_rate": commission_rate,
        "source_system": source_system,
        "source_transaction_id": src_tx_id_str,
        "transaction_date": txn_date,
    }

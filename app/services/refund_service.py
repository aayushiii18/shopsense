"""
services/refund_service.py — Business logic for atomic refund processing and stock return.

Key requirements:
1. Idempotency: Duplicate idempotency_key returns existing refund record without re-processing.
2. Financial Limits: Cumulative refunds cannot exceed transaction net amount (amount - discount_amount).
3. Inventory Return: Cumulative returned quantity cannot exceed transaction purchased quantity.
4. Atomicity: Stock restocking and StockMovement ('RETURN') are committed in the same database transaction.
5. Status Updates: Updates Transaction payment_status to 'PARTIALLY_REFUNDED' or 'REFUNDED'.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException, status
import logging

from app.models.refund import Refund
from app.models.transaction import Transaction
from app.models.inventory import Inventory
from app.models.stock_movement import StockMovement
from app.schemas.refund_schema import RefundCreate
from app.services.revenue_service import _REV_CACHE

logger = logging.getLogger(__name__)


def process_refund(db: Session, payload: RefundCreate) -> Refund:
    """
    Executes an atomic refund with optional inventory restocking.
    Guarantees strict idempotency and boundary validation.
    """
    # 1. Idempotency check: if key already exists, return existing record
    existing = db.query(Refund).filter(Refund.idempotency_key == payload.idempotency_key).first()
    if existing:
        logger.info("Idempotent hit for refund key: %s (id=%s)", payload.idempotency_key, existing.refund_id)
        return existing

    # 2. Fetch transaction
    txn = db.query(Transaction).filter(Transaction.transaction_id == payload.transaction_id).first()
    if not txn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with id={payload.transaction_id} not found.",
        )

    # 3. Validate financial ceiling
    existing_refund_sum = (
        db.query(func.coalesce(func.sum(Refund.amount), 0.0))
        .filter(Refund.transaction_id == payload.transaction_id, Refund.status == "COMPLETED")
        .scalar()
    ) or 0.0

    net_txn_value = round(float(txn.amount) - float(txn.discount_amount or 0.0), 2)
    remaining_refundable = round(net_txn_value - existing_refund_sum, 2)

    if payload.amount > remaining_refundable + 1e-4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Refund amount {payload.amount:.2f} exceeds remaining refundable balance "
                f"{remaining_refundable:.2f} for transaction {payload.transaction_id} "
                f"(Net Value: {net_txn_value:.2f}, Already Refunded: {existing_refund_sum:.2f})."
            ),
        )

    # 4. Validate quantity ceiling
    existing_returned_qty = (
        db.query(func.coalesce(func.sum(Refund.returned_quantity), 0))
        .filter(Refund.transaction_id == payload.transaction_id, Refund.status == "COMPLETED")
        .scalar()
    ) or 0

    remaining_qty = txn.quantity - existing_returned_qty
    if payload.returned_quantity > remaining_qty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Returned quantity {payload.returned_quantity} exceeds remaining refundable quantity "
                f"{remaining_qty} for transaction {payload.transaction_id} "
                f"(Purchased: {txn.quantity}, Already Returned: {existing_returned_qty})."
            ),
        )

    if payload.restock_inventory and payload.returned_quantity == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot restock inventory when returned_quantity is 0.",
        )

    # 5. Create Refund record
    refund = Refund(
        transaction_id=payload.transaction_id,
        idempotency_key=payload.idempotency_key,
        amount=round(payload.amount, 2),
        reason=payload.reason,
        status="COMPLETED",
        restock_inventory=payload.restock_inventory,
        returned_quantity=payload.returned_quantity,
    )
    db.add(refund)
    db.flush()  # assign refund.refund_id

    # 6. Restock inventory and record StockMovement if requested
    if payload.restock_inventory and payload.returned_quantity > 0:
        inv = db.query(Inventory).filter(Inventory.product_id == txn.product_id).first()
        target_wh = inv.warehouse if inv and inv.warehouse else "MAIN"
        if inv:
            inv.current_stock += payload.returned_quantity

        movement = StockMovement(
            product_id=txn.product_id,
            movement_type="RETURN",
            quantity=payload.returned_quantity,
            source_warehouse="CUSTOMER_RETURN",
            target_warehouse=target_wh,
            reference_id=txn.transaction_id,
            notes=f"Restocked via refund key '{payload.idempotency_key}' (refund_id={refund.refund_id})",
        )
        db.add(movement)

    # 7. Update transaction payment status
    new_total_refunded = round(existing_refund_sum + payload.amount, 2)
    if new_total_refunded >= net_txn_value - 1e-4:
        txn.payment_status = "REFUNDED"
    else:
        txn.payment_status = "PARTIALLY_REFUNDED"

    # 8. Commit atomic transaction
    db.commit()
    db.refresh(refund)

    # Clear analytics cache
    _REV_CACHE.clear()

    return refund


def get_refunds_for_transaction(db: Session, transaction_id: int) -> List[Refund]:
    """Retrieve all refund records associated with a transaction."""
    return (
        db.query(Refund)
        .filter(Refund.transaction_id == transaction_id)
        .order_by(Refund.created_at.desc())
        .all()
    )


def get_refund_by_id(db: Session, refund_id: int) -> Optional[Refund]:
    """Retrieve a single refund record by primary key."""
    return db.query(Refund).filter(Refund.refund_id == refund_id).first()

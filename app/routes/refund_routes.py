"""
routes/refund_routes.py — FastAPI endpoints for atomic refunds and returns.

POST /refunds/                         Process atomic refund with idempotency (Loopback-Guarded)
GET  /refunds/{refund_id}              Get refund details by ID
GET  /refunds/transaction/{txn_id}     Get all refunds for a specific transaction
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.transaction import Transaction
from app.models.user import User, UserRole
from app.schemas.refund_schema import RefundCreate, RefundResponse
from app.services import refund_service
from app.core.dependencies import require_admin, get_current_user

router = APIRouter(prefix="/refunds", tags=["Refunds & Returns"])


@router.post(
    "/",
    response_model=RefundResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Process atomic refund (Admin Only)",
    dependencies=[Depends(require_admin)],
)
def create_refund(payload: RefundCreate, db: Session = Depends(get_db)):
    """
    Issues a full or partial refund for a completed transaction.

    Safeguards:
    - Enforces idempotent key deduplication.
    - Validates cumulative refund does not exceed net transaction value.
    - Validates returned quantity does not exceed original purchased quantity.
    - Restocks inventory atomically and logs StockMovement ('RETURN') if requested.
    - Updates transaction payment status to PARTIALLY_REFUNDED or REFUNDED.
    - Restricted to local administrative loopback interface (interim security gate).
    """
    return refund_service.process_refund(db, payload)


@router.get(
    "/{refund_id}",
    response_model=RefundResponse,
    summary="Get refund by ID",
)
def get_refund(
    refund_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve an individual refund record with role-based access validation."""
    refund = refund_service.get_refund_by_id(db, refund_id)
    if not refund:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Refund with id={refund_id} not found.",
        )

    if current_user.role == UserRole.VENDOR:
        txn = db.query(Transaction).filter(Transaction.transaction_id == refund.transaction_id).first()
        if txn and txn.vendor_id != current_user.vendor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access forbidden: You cannot view refund details for another vendor's transaction.",
            )
    elif current_user.role == UserRole.CUSTOMER:
        txn = db.query(Transaction).filter(Transaction.transaction_id == refund.transaction_id).first()
        if txn and txn.customer_id != current_user.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access forbidden: You cannot view refund details for another customer's transaction.",
            )

    return refund


@router.get(
    "/transaction/{transaction_id}",
    response_model=List[RefundResponse],
    summary="List refunds for a transaction",
)
def list_transaction_refunds(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve all refund history records for a transaction with tenant verification."""
    txn = db.query(Transaction).filter(Transaction.transaction_id == transaction_id).first()
    if txn:
        if current_user.role == UserRole.VENDOR and txn.vendor_id != current_user.vendor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access forbidden: You cannot view refunds for another vendor's transaction.",
            )
        elif current_user.role == UserRole.CUSTOMER and txn.customer_id != current_user.customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access forbidden: You cannot view refunds for another customer's transaction.",
            )

    return refund_service.get_refunds_for_transaction(db, transaction_id)

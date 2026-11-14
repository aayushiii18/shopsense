"""
services/vendor_service.py — Business logic for multi-vendor lifecycle governance.

Implements the formal Vendor Lifecycle State Machine:
  PENDING_APPROVAL -> ACTIVE, REJECTED
  ACTIVE           -> SUSPENDED, TERMINATED
  LEGACY_ACTIVE    -> SUSPENDED, TERMINATED
  SUSPENDED        -> ACTIVE, TERMINATED
  REJECTED         -> PENDING_APPROVAL
  TERMINATED       -> [Terminal state, no further transitions permitted]

Also handles tier assignments and operational compliance.
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.vendor import Vendor
from app.schemas.vendor_schema import VALID_COMMISSION_TIERS

ALLOWED_TRANSITIONS = {
    "PENDING_APPROVAL": {"ACTIVE", "REJECTED"},
    "ACTIVE": {"SUSPENDED", "TERMINATED"},
    "LEGACY_ACTIVE": {"SUSPENDED", "TERMINATED"},
    "SUSPENDED": {"ACTIVE", "TERMINATED"},
    "REJECTED": {"PENDING_APPROVAL"},
    "TERMINATED": set(),  # Terminal state
}


def transition_vendor_status(
    db: Session,
    vendor_id: int,
    new_status: str,
    notes: Optional[str] = None,
    compliance_status: Optional[str] = None,
    commission_tier: Optional[str] = None,
) -> Vendor:
    """
    Executes a validated state machine transition for a vendor.
    Rejects illegal transitions with HTTP 400.
    """
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor with id={vendor_id} not found.",
        )

    current_status = vendor.status
    if current_status == new_status:
        # Idempotent no-op on status, allow updating notes or tier
        pass
    else:
        allowed = ALLOWED_TRANSITIONS.get(current_status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Illegal vendor status transition from '{current_status}' to '{new_status}'. "
                    f"Permitted transitions from '{current_status}': {sorted(list(allowed)) or 'None (Terminal state)'}."
                ),
            )
        vendor.status = new_status

    if notes is not None:
        vendor.verification_notes = notes

    if compliance_status is not None:
        vendor.compliance_status = compliance_status

    if commission_tier is not None:
        if commission_tier not in VALID_COMMISSION_TIERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid commission tier '{commission_tier}'. Valid tiers: {list(VALID_COMMISSION_TIERS.keys())}",
            )
        vendor.commission_tier = commission_tier
        vendor.commission_rate = VALID_COMMISSION_TIERS[commission_tier]

    db.commit()
    db.refresh(vendor)
    return vendor


def verify_vendor_can_list_products(vendor: Vendor) -> None:
    """
    Enforces business restriction:
    Suspended, Terminated, or Rejected vendors cannot list new products.
    """
    if vendor.status in {"SUSPENDED", "TERMINATED", "REJECTED"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Vendor id={vendor.id} is in status '{vendor.status}'. Inactive vendors cannot list products.",
        )

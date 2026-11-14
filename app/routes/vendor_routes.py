"""
routes/vendor_routes.py — FastAPI endpoints for multi-vendor management and lifecycle governance.

POST /vendors/               Register a new vendor (status defaults to PENDING_APPROVAL)
GET  /vendors/               List all vendors (paginated, optional status filter)
GET  /vendors/{id}           Get a single vendor by ID
PUT  /vendors/{id}           Update vendor contact/profile info
PUT  /vendors/{id}/status    Transition vendor lifecycle state (interim loopback-guarded)
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.vendor import Vendor
from app.schemas.vendor_schema import (
    VendorCreate,
    VendorUpdate,
    VendorStatusUpdate,
    VendorResponse,
    VALID_COMMISSION_TIERS,
)
from app.services import vendor_service
from app.core.security import verify_loopback_only

router = APIRouter(prefix="/vendors", tags=["Vendors"])


@router.post(
    "/",
    response_model=VendorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new vendor",
)
def create_vendor(payload: VendorCreate, db: Session = Depends(get_db)):
    """
    Register a new vendor on the platform.
    New vendors are enrolled in PENDING_APPROVAL with assigned commission tier.
    """
    existing = db.query(Vendor).filter(Vendor.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A vendor with email '{payload.email}' is already registered.",
        )

    tier = payload.commission_tier or "TIER_STANDARD"
    rate = VALID_COMMISSION_TIERS.get(tier, 0.12)

    vendor = Vendor(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        address=payload.address,
        tax_id=payload.tax_id,
        business_type=payload.business_type,
        status="PENDING_APPROVAL",
        commission_tier=tier,
        commission_rate=rate,
        compliance_status="PENDING_REVIEW",
    )
    db.add(vendor)
    try:
        db.commit()
        db.refresh(vendor)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A vendor with email '{payload.email}' is already registered.",
        )
    return vendor


@router.get(
    "/",
    response_model=list[VendorResponse],
    summary="List all vendors",
)
def list_vendors(
    skip: int = 0,
    limit: int = 100,
    status_filter: str | None = Query(default=None, alias="status", description="Filter by status"),
    db: Session = Depends(get_db),
):
    """Return a paginated list of all registered vendors."""
    if limit > 500:
        raise HTTPException(status_code=400, detail="limit cannot exceed 500.")
    query = db.query(Vendor)
    if status_filter:
        query = query.filter(Vendor.status == status_filter.upper())
    return query.offset(skip).limit(limit).all()


@router.get(
    "/{vendor_id}",
    response_model=VendorResponse,
    summary="Get vendor by ID",
)
def get_vendor(vendor_id: int, db: Session = Depends(get_db)):
    """Return a single vendor record, or 404 if not found."""
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor with id={vendor_id} not found.",
        )
    return vendor


@router.put(
    "/{vendor_id}",
    response_model=VendorResponse,
    summary="Update vendor details",
)
def update_vendor(vendor_id: int, payload: VendorUpdate, db: Session = Depends(get_db)):
    """Update an existing vendor record contact details."""
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor with id={vendor_id} not found.",
        )
    if payload.email and payload.email != vendor.email:
        conflict = db.query(Vendor).filter(Vendor.email == payload.email, Vendor.id != vendor_id).first()
        if conflict:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A vendor with email '{payload.email}' is already registered.",
            )
        vendor.email = payload.email
    if payload.name:
        vendor.name = payload.name
    if payload.phone:
        vendor.phone = payload.phone
    if payload.address is not None:
        vendor.address = payload.address
    if payload.tax_id is not None:
        vendor.tax_id = payload.tax_id
    if payload.business_type is not None:
        vendor.business_type = payload.business_type

    db.commit()
    db.refresh(vendor)
    return vendor


@router.put(
    "/{vendor_id}/status",
    response_model=VendorResponse,
    summary="Transition vendor lifecycle state (Loopback-Guarded)",
    dependencies=[Depends(verify_loopback_only)],
)
def update_vendor_status(
    vendor_id: int,
    payload: VendorStatusUpdate,
    db: Session = Depends(get_db),
):
    """
    Executes a formal lifecycle state transition for a vendor.
    Protected by the interim loopback security gate (127.0.0.1 / ::1).
    """
    return vendor_service.transition_vendor_status(
        db=db,
        vendor_id=vendor_id,
        new_status=payload.status,
        notes=payload.verification_notes,
        compliance_status=payload.compliance_status,
        commission_tier=payload.commission_tier,
    )

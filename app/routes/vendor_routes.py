"""
routes/vendor_routes.py — FastAPI endpoints for vendor management.

POST /vendors/        Register a new vendor
GET  /vendors/        List all vendors (paginated)
GET  /vendors/{id}    Get a single vendor by ID
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.vendor import Vendor
from app.schemas.vendor_schema import VendorCreate, VendorResponse

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

    - Validates email format and all required fields (handled by Pydantic).
    - Returns HTTP 409 if the email is already registered.
    """
    # Check for duplicate email (belt-and-suspenders; DB unique constraint is the final guard)
    existing = db.query(Vendor).filter(Vendor.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A vendor with email '{payload.email}' is already registered.",
        )

    vendor = Vendor(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        address=payload.address,
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
def list_vendors(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Return a paginated list of all registered vendors."""
    if limit > 500:
        raise HTTPException(status_code=400, detail="limit cannot exceed 500.")
    vendors = db.query(Vendor).offset(skip).limit(limit).all()
    return vendors


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

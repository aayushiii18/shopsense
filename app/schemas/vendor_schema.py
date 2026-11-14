"""
schemas/vendor_schema.py — Pydantic models for vendor request/response validation.

VendorCreate       : fields required when registering a new vendor (request body).
VendorUpdate       : fields for updating vendor contact/profile info.
VendorStatusUpdate : fields for lifecycle state machine transitions and tier assignments.
VendorResponse     : fields returned in API responses (includes status and commission tier).
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict
import re


VALID_COMMISSION_TIERS = {
    "TIER_STARTER": 0.15,
    "TIER_STANDARD": 0.12,
    "TIER_PREFERRED": 0.10,
    "TIER_ENTERPRISE": 0.08,
}

VALID_STATUSES = {"PENDING_APPROVAL", "ACTIVE", "LEGACY_ACTIVE", "SUSPENDED", "TERMINATED", "REJECTED"}
VALID_COMPLIANCE = {"PENDING_REVIEW", "VERIFIED", "FLAGGED", "LEGACY_EXEMPT"}


class VendorCreate(BaseModel):
    """Schema used when a client registers a new vendor."""

    name: str
    email: EmailStr
    phone: str
    address: str | None = None
    tax_id: str | None = None
    business_type: str | None = None
    commission_tier: str = "TIER_STANDARD"

    @field_validator("email", mode="before")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        """Normalise email to lowercase for consistent duplicate detection."""
        if isinstance(v, str):
            return v.lower().strip()
        return v

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Vendor name must not be blank.")
        if len(v) > 150:
            raise ValueError("Vendor name must be 150 characters or fewer.")
        return v

    @field_validator("phone")
    @classmethod
    def phone_must_be_valid(cls, v: str) -> str:
        """Accept digits, spaces, hyphens, plus sign, and parentheses."""
        v = v.strip()
        if not v:
            raise ValueError("Phone number must not be blank.")
        if not re.fullmatch(r"[\d\s\-\+\(\)]{7,20}", v):
            raise ValueError(
                "Phone number must be 7–20 characters and contain only digits, "
                "spaces, hyphens, plus signs, or parentheses."
            )
        return v

    @field_validator("address")
    @classmethod
    def address_length(cls, v: str | None) -> str | None:
        if v is not None and len(v.strip()) > 400:
            raise ValueError("Address must be 400 characters or fewer.")
        return v

    @field_validator("commission_tier")
    @classmethod
    def validate_tier(cls, v: str) -> str:
        if v not in VALID_COMMISSION_TIERS:
            raise ValueError(f"Invalid commission tier '{v}'. Must be one of: {list(VALID_COMMISSION_TIERS.keys())}")
        return v


class VendorUpdate(BaseModel):
    """Schema used when updating an existing vendor."""

    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None
    tax_id: str | None = None
    business_type: str | None = None

    @field_validator("email", mode="before")
    @classmethod
    def normalise_email(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            return v.lower().strip()
        return v

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Vendor name must not be blank.")
            if len(v) > 150:
                raise ValueError("Vendor name must be 150 characters or fewer.")
        return v

    @field_validator("phone")
    @classmethod
    def phone_must_be_valid(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Phone number must not be blank.")
            if not re.fullmatch(r"[\d\s\-\+\(\)]{7,20}", v):
                raise ValueError(
                    "Phone number must be 7–20 characters and contain only digits, "
                    "spaces, hyphens, plus signs, or parentheses."
                )
        return v

    @field_validator("address")
    @classmethod
    def address_length(cls, v: str | None) -> str | None:
        if v is not None and len(v.strip()) > 400:
            raise ValueError("Address must be 400 characters or fewer.")
        return v


class VendorStatusUpdate(BaseModel):
    """Schema for controlling vendor lifecycle state machine transitions."""

    status: str
    verification_notes: Optional[str] = None
    compliance_status: Optional[str] = None
    commission_tier: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{v}'. Must be one of: {list(VALID_STATUSES)}")
        return v

    @field_validator("compliance_status")
    @classmethod
    def validate_compliance(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip().upper()
            if v not in VALID_COMPLIANCE:
                raise ValueError(f"Invalid compliance_status '{v}'. Must be one of: {list(VALID_COMPLIANCE)}")
        return v

    @field_validator("commission_tier")
    @classmethod
    def validate_tier(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip().upper()
            if v not in VALID_COMMISSION_TIERS:
                raise ValueError(f"Invalid commission tier '{v}'. Must be one of: {list(VALID_COMMISSION_TIERS.keys())}")
        return v


class VendorResponse(BaseModel):
    """Schema returned to the client after vendor creation or lookup."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    phone: str
    address: str | None
    status: str = "PENDING_APPROVAL"
    commission_tier: str = "TIER_STANDARD"
    commission_rate: float = 0.12
    compliance_status: str = "PENDING_REVIEW"
    tax_id: str | None = None
    business_type: str | None = None
    verification_notes: str | None = None
    created_at: datetime

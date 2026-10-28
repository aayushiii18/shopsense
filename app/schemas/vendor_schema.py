"""
schemas/vendor_schema.py — Pydantic models for vendor request/response validation.

VendorCreate  : fields required when registering a new vendor (request body).
VendorResponse: fields returned in API responses (includes DB-generated fields).
"""

from datetime import datetime
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict
import re


class VendorCreate(BaseModel):
    """Schema used when a client registers a new vendor."""

    name: str
    email: EmailStr
    phone: str
    address: str | None = None

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


class VendorResponse(BaseModel):
    """Schema returned to the client after vendor creation or lookup."""

    model_config = ConfigDict(from_attributes=True)  # allows ORM → Pydantic

    id: int
    name: str
    email: str
    phone: str
    address: str | None
    created_at: datetime

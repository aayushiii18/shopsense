"""
app/schemas/auth_schema.py — Pydantic schemas for Authentication and RBAC.

Stage 7: Authentication, JWT Security, RBAC & Multi-Tenant Access Control.
"""

from datetime import datetime
import re
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, ConfigDict


class UserRegisterRequest(BaseModel):
    """Public customer registration schema."""
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters.")
    customer_id: Optional[int] = Field(None, description="Optional existing customer ID to associate.")

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return v


class UserLoginRequest(BaseModel):
    """User credential login schema."""
    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    """Token refresh schema."""
    refresh_token: str = Field(..., description="Valid JWT refresh token.")


class ChangePasswordRequest(BaseModel):
    """Self-service password change schema."""
    current_password: str
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("New password must be at least 8 characters long.")
        return v


class AdminCreateUserRequest(BaseModel):
    """Administrative user creation schema."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str = Field(..., description="Role: 'ADMIN', 'VENDOR', or 'CUSTOMER'.")
    vendor_id: Optional[int] = None
    customer_id: Optional[int] = None
    is_active: bool = True
    is_verified: bool = True

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        v_upper = v.upper()
        if v_upper not in {"ADMIN", "VENDOR", "CUSTOMER"}:
            raise ValueError("Role must be one of: 'ADMIN', 'VENDOR', 'CUSTOMER'.")
        return v_upper


class AdminUpdateUserStatusRequest(BaseModel):
    """Administrative user status update schema."""
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None


class AdminUpdateUserRoleRequest(BaseModel):
    """Administrative user role update schema."""
    role: str
    vendor_id: Optional[int] = None
    customer_id: Optional[int] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        v_upper = v.upper()
        if v_upper not in {"ADMIN", "VENDOR", "CUSTOMER"}:
            raise ValueError("Role must be one of: 'ADMIN', 'VENDOR', 'CUSTOMER'.")
        return v_upper


class TokenResponse(BaseModel):
    """OAuth2 compatible JWT response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: int
    email: str
    role: str
    vendor_id: Optional[int] = None
    customer_id: Optional[int] = None


class UserResponse(BaseModel):
    """Public user profile response."""
    id: int
    email: str
    role: str
    vendor_id: Optional[int] = None
    customer_id: Optional[int] = None
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    """Generic status/message response."""
    message: str
    detail: Optional[str] = None


class VendorRegisterRequest(BaseModel):
    """Public self-service vendor onboarding & authentication registration schema."""
    owner_name: str = Field(..., min_length=1, max_length=150, description="Owner full name")
    business_name: str = Field(..., min_length=1, max_length=150, description="Business or store name")
    email: EmailStr = Field(..., description="Official vendor account email")
    phone: str = Field(..., description="Business phone number (7-20 chars)")
    category: str = Field(..., min_length=1, max_length=100, description="Primary vendor category")
    tax_id: Optional[str] = Field(None, max_length=100, description="Optional Tax / GST registration ID")
    address: Optional[str] = Field(None, max_length=400, description="Optional business address")
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")
    password_confirmation: str = Field(..., min_length=8, description="Password confirmation")

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @field_validator("owner_name", "business_name", "category")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field must not be blank.")
        return cleaned

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = v.strip()
        if not re.fullmatch(r"[\d\s\-\+\(\)]{7,20}", cleaned):
            raise ValueError(
                "Phone number must be 7-20 characters and contain only digits, spaces, hyphens, plus signs, or parentheses."
            )
        return cleaned

    @field_validator("tax_id")
    @classmethod
    def normalize_tax_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            return None
        if len(cleaned) < 3 or len(cleaned) > 100:
            raise ValueError("Tax/GST ID must be between 3 and 100 characters when provided.")
        if not re.fullmatch(r"[A-Za-z0-9\-\s/]+", cleaned):
            raise ValueError("Tax/GST ID contains invalid characters.")
        return cleaned.upper()

    @field_validator("address")
    @classmethod
    def normalize_address(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8 or not v.strip():
            raise ValueError("Password must be at least 8 non-whitespace characters.")
        return v

    @model_validator(mode="after")
    def verify_password_match(self) -> "VendorRegisterRequest":
        if self.password != self.password_confirmation:
            raise ValueError("Password and password confirmation do not match.")
        return self


class VendorRegisterResponse(BaseModel):
    """Unified onboarding response after atomic Vendor + User creation."""
    user_id: int
    vendor_id: int
    email: str
    role: str
    owner_name: str
    business_name: str
    category: str
    tax_id: Optional[str] = None
    vendor_status: str
    compliance_status: str
    is_active: bool
    is_verified: bool
    message: str

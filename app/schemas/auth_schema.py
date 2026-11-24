"""
app/schemas/auth_schema.py — Pydantic schemas for Authentication and RBAC.

Stage 7: Authentication, JWT Security, RBAC & Multi-Tenant Access Control.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator


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

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    """Generic status/message response."""
    message: str
    detail: Optional[str] = None

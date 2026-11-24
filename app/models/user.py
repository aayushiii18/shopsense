"""
app/models/user.py — SQLAlchemy ORM models for Users and Refresh Tokens.

Stage 7: Authentication, JWT Security, RBAC & Multi-Tenant Access Control.
Roles:
- ADMIN: Complete system oversight, user management, financial approvals, ETL.
- VENDOR: Tenant-isolated product catalog, stock movements, vendor-specific analytics.
- CUSTOMER: Personal profile, customer-level recommendations, order history.
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    CheckConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class UserRole:
    ADMIN = "ADMIN"
    VENDOR = "VENDOR"
    CUSTOMER = "CUSTOMER"

    ALL_ROLES = {ADMIN, VENDOR, CUSTOMER}


class User(Base):
    """
    User entity for authentication, identity and role-based access control.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default=UserRole.CUSTOMER, index=True)

    # Optional multi-tenant entity linkage
    vendor_id = Column(Integer, ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.customer_id", ondelete="SET NULL"), nullable=True, index=True)

    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login_at = Column(DateTime, nullable=True)

    # ORM Relationships
    vendor = relationship("Vendor", backref="user_account", uselist=False)
    customer = relationship("Customer", backref="user_account", uselist=False)
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "role IN ('ADMIN', 'VENDOR', 'CUSTOMER')",
            name="ck_users_role",
        ),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email='{self.email}' role='{self.role}'>"


class RefreshToken(Base):
    """
    Refresh Token record for rotation, family reuse detection, and revocation.
    Stores SHA-256 hash of the refresh token string for defense-in-depth.
    """
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    token_family = Column(String(36), nullable=False, index=True)
    jti = Column(String(36), unique=True, nullable=False)

    is_revoked = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    # ORM Relationship
    user = relationship("User", back_populates="refresh_tokens")

    def __repr__(self) -> str:
        return (
            f"<RefreshToken id={self.id} user_id={self.user_id} "
            f"family='{self.token_family}' is_revoked={self.is_revoked}>"
        )

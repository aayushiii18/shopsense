"""
models/vendor.py — ORM model for the vendors table.

A vendor is an independent seller registered on the StockPilot platform.
Includes lifecycle status, commission tier, and compliance fields.
"""

from datetime import datetime
from sqlalchemy import Integer, String, Float, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="PENDING_APPROVAL", nullable=False
    )
    commission_tier: Mapped[str] = mapped_column(
        String(50), default="TIER_STANDARD", nullable=False
    )
    commission_rate: Mapped[float] = mapped_column(
        Float, default=0.12, nullable=False
    )
    tax_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    business_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    compliance_status: Mapped[str] = mapped_column(
        String(50), default="PENDING_REVIEW", nullable=False
    )
    verification_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships (back-populated from Product, Transaction, and Settlements)
    products: Mapped[list["Product"]] = relationship(  # noqa: F821
        "Product", back_populates="vendor", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["Transaction"]] = relationship(  # noqa: F821
        "Transaction", back_populates="vendor"
    )
    settlements: Mapped[list["VendorSettlement"]] = relationship(  # noqa: F821
        "VendorSettlement", back_populates="vendor", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Vendor id={self.id} name={self.name!r} status={self.status} tier={self.commission_tier}>"

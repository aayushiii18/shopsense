"""
models/vendor_settlement.py — ORM model for the vendor_settlements ledger table.

Records auditable vendor settlement sheets, calculating gross sales,
discounts, refunds, platform commissions, and payable net amounts.
"""

from datetime import datetime
from sqlalchemy import Integer, Float, String, DateTime, ForeignKey, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class VendorSettlement(Base):
    __tablename__ = "vendor_settlements"

    __table_args__ = (
        CheckConstraint("gross_sales >= 0", name="ck_settlement_gross_nonnegative"),
        CheckConstraint("net_sales >= 0", name="ck_settlement_net_nonnegative"),
        CheckConstraint("effective_commission_rate >= 0", name="ck_settlement_rate_nonnegative"),
    )

    settlement_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    vendor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    gross_sales: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    discounts_allocated: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    refunds_deducted: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    net_sales: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    commission_tier: Mapped[str] = mapped_column(String(50), default="TIER_STANDARD", nullable=False)
    effective_commission_rate: Mapped[float] = mapped_column(Float, default=0.12, nullable=False)
    platform_commission: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    vendor_payout: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    settlement_status: Mapped[str] = mapped_column(String(50), default="DRAFT", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationship
    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="settlements")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<VendorSettlement settlement_id={self.settlement_id} vendor_id={self.vendor_id} "
            f"net_sales={self.net_sales} payout={self.vendor_payout} status={self.settlement_status}>"
        )

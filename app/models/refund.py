"""
models/refund.py — ORM model for the refunds table.

Records full and partial return and refund operations.
Enforces idempotency, amount constraints, inventory restocking, and audit links.
"""

from datetime import datetime
from sqlalchemy import Integer, Float, String, Boolean, DateTime, ForeignKey, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Refund(Base):
    __tablename__ = "refunds"

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_refund_amount_positive"),
        CheckConstraint("returned_quantity >= 0", name="ck_refund_returned_quantity_nonnegative"),
    )

    refund_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    transaction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("transactions.transaction_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="COMPLETED", nullable=False)
    restock_inventory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    returned_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    transaction: Mapped["Transaction"] = relationship("Transaction", back_populates="refunds")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<Refund refund_id={self.refund_id} transaction_id={self.transaction_id} "
            f"amount={self.amount} status={self.status} idempotency_key={self.idempotency_key!r}>"
        )

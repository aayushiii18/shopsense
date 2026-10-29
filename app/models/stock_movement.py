"""
models/stock_movement.py — ORM model for the stock_movements table.

Maintains an immutable audit trail of all inventory events (restocking, sales, adjustments, transfers).
Powers real-time inventory tracking, turnover analysis, and replenishment planning.
"""

from datetime import datetime
from sqlalchemy import Integer, String, DateTime, ForeignKey, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym
from app.database import Base


class StockMovement(Base):
    __tablename__ = "stock_movements"

    __table_args__ = (
        CheckConstraint("quantity != 0", name="ck_stock_movement_quantity_nonzero"),
    )

    movement_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    movement_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # RESTOCK, SALE, ADJUSTMENT, TRANSFER, RETURN
    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # positive for additions, negative for deductions
    source_warehouse: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_warehouse: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reference_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # linked transaction_id or purchase_order_id
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Convenience synonym
    id = synonym("movement_id")

    # Relationship
    product: Mapped["Product"] = relationship("Product", back_populates="stock_movements")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<StockMovement id={self.movement_id} product_id={self.product_id} "
            f"type={self.movement_type!r} qty={self.quantity}>"
        )

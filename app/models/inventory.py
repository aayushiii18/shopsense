"""
models/inventory.py — ORM model for the inventory table.

Tracks current stock level, warehouse location, and reorder threshold for each product.
One-to-one relationship: one product -> one inventory record.
"""

from datetime import datetime
from sqlalchemy import Integer, String, DateTime, ForeignKey, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Inventory(Base):
    __tablename__ = "inventory"

    __table_args__ = (
        CheckConstraint("current_stock >= 0", name="ck_inventory_current_stock_non_negative"),
        CheckConstraint("reorder_level >= 0", name="ck_inventory_reorder_level_non_negative"),
    )

    inventory_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        unique=True,   # enforces one-to-one
        nullable=False,
        index=True,
    )
    current_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warehouse: Mapped[str] = mapped_column(String(100), nullable=False, default="Main Warehouse")
    reorder_level: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationship
    product: Mapped["Product"] = relationship("Product", back_populates="inventory")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<Inventory inventory_id={self.inventory_id} product_id={self.product_id} "
            f"current_stock={self.current_stock} warehouse={self.warehouse!r} "
            f"reorder_level={self.reorder_level}>"
        )

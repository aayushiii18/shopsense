"""
models/product.py — ORM model for the products table.

Each product belongs to exactly one vendor and has an optional
inventory record tracking its stock level.
"""

from datetime import datetime
from sqlalchemy import Integer, String, Float, DateTime, ForeignKey, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Product(Base):
    __tablename__ = "products"

    __table_args__ = (
        CheckConstraint("price > 0", name="ck_product_price_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    parent_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vendor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="products")  # noqa: F821
    inventory: Mapped["Inventory | None"] = relationship(  # noqa: F821
        "Inventory", back_populates="product", uselist=False, cascade="all, delete-orphan"
    )
    transactions: Mapped[list["Transaction"]] = relationship(  # noqa: F821
        "Transaction", back_populates="product"
    )
    stock_movements: Mapped[list["StockMovement"]] = relationship(  # noqa: F821
        "StockMovement", back_populates="product", cascade="all, delete-orphan"
    )
    interactions: Mapped[list["CustomerInteraction"]] = relationship(  # noqa: F821
        "CustomerInteraction", back_populates="product", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id} name={self.name!r} price={self.price}>"

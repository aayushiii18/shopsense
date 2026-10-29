"""
models/transaction.py — ORM model for the transactions table.

Records each sale event. The amount field represents the total monetary value
of the transaction (quantity * unit_price).
"""

from datetime import datetime
from sqlalchemy import Integer, Float, DateTime, ForeignKey, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym
from app.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_transaction_quantity_positive"),
        CheckConstraint("unit_price > 0", name="ck_transaction_unit_price_positive"),
        CheckConstraint("amount > 0", name="ck_transaction_amount_positive"),
    )

    transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    vendor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.customer_id", ondelete="SET NULL"), nullable=True, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    transaction_date: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Backward compatibility synonym
    total_price = synonym("amount")

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="transactions")  # noqa: F821
    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="transactions")  # noqa: F821
    customer: Mapped["Customer | None"] = relationship("Customer", back_populates="transactions")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<Transaction transaction_id={self.transaction_id} product_id={self.product_id} "
            f"quantity={self.quantity} amount={self.amount}>"
        )

"""
models/customer.py — ORM model for the customers table.

Represents an individual retail customer on the ShopSense platform.
Used for customer behavioral analytics, RFM segmentation, and personalized recommendations.
"""

from datetime import datetime
from sqlalchemy import Integer, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym
from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    signup_date: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Convenience synonym
    id = synonym("customer_id")

    # Relationships
    transactions: Mapped[list["Transaction"]] = relationship(  # noqa: F821
        "Transaction", back_populates="customer"
    )
    interactions: Mapped[list["CustomerInteraction"]] = relationship(  # noqa: F821
        "CustomerInteraction", back_populates="customer", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Customer id={self.customer_id} name={self.name!r} email={self.email!r}>"

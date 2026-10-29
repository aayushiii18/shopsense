"""
models/customer_interaction.py — ORM model for the customer_interactions table.

Tracks implicit and explicit interactions between customers and products
(e.g., views, cart additions, ratings, and purchases) to power the recommendation engine.
"""

from datetime import datetime
from sqlalchemy import Integer, String, Float, DateTime, ForeignKey, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym
from app.database import Base


class CustomerInteraction(Base):
    __tablename__ = "customer_interactions"

    __table_args__ = (
        CheckConstraint("interaction_weight > 0", name="ck_interaction_weight_positive"),
    )

    interaction_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.customer_id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    interaction_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'view', 'add_to_cart', 'purchase', 'rating'
    interaction_weight: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0
    )
    interaction_date: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Convenience synonym
    id = synonym("interaction_id")

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="interactions")  # noqa: F821
    product: Mapped["Product"] = relationship("Product", back_populates="interactions")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<CustomerInteraction id={self.interaction_id} customer={self.customer_id} "
            f"product={self.product_id} type={self.interaction_type!r}>"
        )

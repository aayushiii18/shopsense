"""
schemas/refund_schema.py — Pydantic models for refund operations and responses.

RefundCreate   : fields submitted when requesting a refund.
RefundResponse : fields returned to client with idempotency and audit details.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator, ConfigDict


class RefundCreate(BaseModel):
    """Schema used when submitting a refund request."""

    transaction_id: int
    amount: float
    idempotency_key: str
    reason: Optional[str] = None
    restock_inventory: bool = False
    returned_quantity: int = 0

    @field_validator("transaction_id")
    @classmethod
    def transaction_id_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("transaction_id must be a positive integer.")
        return v

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Refund amount must be greater than zero.")
        return round(v, 2)

    @field_validator("idempotency_key")
    @classmethod
    def idempotency_key_valid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("idempotency_key must not be blank.")
        if len(v) > 100:
            raise ValueError("idempotency_key cannot exceed 100 characters.")
        return v

    @field_validator("returned_quantity")
    @classmethod
    def returned_quantity_valid(cls, v: int) -> int:
        if v < 0:
            raise ValueError("returned_quantity cannot be negative.")
        return v


class RefundResponse(BaseModel):
    """Schema returned after a refund is processed or queried."""

    model_config = ConfigDict(from_attributes=True)

    refund_id: int
    transaction_id: int
    idempotency_key: str
    amount: float
    reason: Optional[str] = None
    status: str
    restock_inventory: bool
    returned_quantity: int
    created_at: datetime

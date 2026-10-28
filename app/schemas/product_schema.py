"""
schemas/product_schema.py — Pydantic models for product request/response validation.

ProductCreate  : fields required when registering a new product.
ProductResponse: fields returned in API responses.
"""

from datetime import datetime
from pydantic import BaseModel, field_validator, ConfigDict


class ProductCreate(BaseModel):
    """Schema used when a client registers a new product."""

    name: str
    description: str | None = None
    price: float
    category: str | None = None
    vendor_id: int

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Product name must not be blank.")
        if len(v) > 200:
            raise ValueError("Product name must be 200 characters or fewer.")
        return v

    @field_validator("price")
    @classmethod
    def price_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Price must be greater than zero.")
        return round(v, 2)

    @field_validator("description")
    @classmethod
    def description_length(cls, v: str | None) -> str | None:
        if v is not None and len(v.strip()) > 1000:
            raise ValueError("Description must be 1000 characters or fewer.")
        return v

    @field_validator("vendor_id")
    @classmethod
    def vendor_id_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("vendor_id must be a positive integer.")
        return v


class ProductResponse(BaseModel):
    """Schema returned to the client after product creation or lookup."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    price: float
    category: str | None
    vendor_id: int
    created_at: datetime

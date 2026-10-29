"""
schemas/inventory_schema.py — Pydantic schemas for inventory endpoints.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


class StockMovementCreate(BaseModel):
    product_id: int = Field(..., gt=0, description="Product ID to record movement for")
    movement_type: Literal["RESTOCK", "SALE", "ADJUSTMENT", "TRANSFER", "RETURN"] = Field(
        ..., description="Type of stock movement"
    )
    quantity: int = Field(..., description="Quantity of movement (cannot be 0)")
    source_warehouse: Optional[str] = Field(None, max_length=100)
    target_warehouse: Optional[str] = Field(None, max_length=100)
    reference_id: Optional[int] = Field(None, description="Linked transaction or PO ID")
    notes: Optional[str] = Field(None, max_length=255)


class StockMovementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    movement_id: int
    product_id: int
    movement_type: str
    quantity: int
    source_warehouse: Optional[str] = None
    target_warehouse: Optional[str] = None
    reference_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: str

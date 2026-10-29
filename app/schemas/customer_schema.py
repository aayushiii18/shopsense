"""
schemas/customer_schema.py — Pydantic schemas for customer endpoints.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, EmailStr, ConfigDict


class CustomerBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    email: EmailStr
    city: Optional[str] = Field(None, max_length=100)
    region: Optional[str] = Field(None, max_length=100)


class CustomerCreate(CustomerBase):
    pass


class CustomerResponse(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    signup_date: datetime


class CustomerRFMResponse(BaseModel):
    customer_id: int
    name: str
    email: str
    city: Optional[str] = None
    recency_days: int
    frequency: int
    monetary: float
    avg_order_value: float


class ClusterProfileResponse(BaseModel):
    cluster_id: int
    segment_name: str
    description: str
    customer_count: int
    avg_recency_days: float
    avg_frequency: float
    avg_monetary: float
    avg_order_value: float
    cluster_silhouette: float

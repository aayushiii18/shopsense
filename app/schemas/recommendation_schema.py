"""
schemas/recommendation_schema.py — Pydantic schemas for recommendation engine.
"""

from typing import Optional, List
from pydantic import BaseModel


class RecommendedProduct(BaseModel):
    product_id: int
    product_name: str
    category: Optional[str] = None
    parent_category: Optional[str] = None
    price: float
    vendor_name: str
    score: float
    recommendation_type: str
    rationale: str


class RecommendationResponse(BaseModel):
    customer_id: int
    customer_name: str
    is_personalized: bool
    recommendation_count: int
    recommendations: List[RecommendedProduct]


class RecommendationEvaluationResponse(BaseModel):
    evaluation_k: int
    sample_size_users: int
    mean_precision_at_k: float
    mean_recall_at_k: float
    hit_rate_at_k: float
    split_method: Optional[str] = None
    message: Optional[str] = None

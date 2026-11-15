"""
schemas/recommendation_schema.py — Pydantic schemas for recommendation engine,
including Collaborative, Content-Based, and Hybrid models.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class RecommendedProduct(BaseModel):
    product_id: int
    product_name: str
    category: Optional[str] = None
    parent_category: Optional[str] = None
    price: float
    vendor_name: str
    score: float
    recommendation_type: str  # "HYBRID", "COLLABORATIVE", "CONTENT_BASED", "POPULARITY_FALLBACK"
    cf_score: Optional[float] = None
    content_score: Optional[float] = None
    rationale: str


class RecommendationResponse(BaseModel):
    customer_id: int
    customer_name: str
    is_personalized: bool
    recommendation_count: int
    recommendation_engine: str = "Collaborative-Filtering"
    recommendations: List[RecommendedProduct]


class HybridRecommendationResponse(BaseModel):
    customer_id: int
    customer_name: str
    is_personalized: bool
    alpha_weight_cf: float
    beta_weight_content: float
    recommendation_count: int
    recommendations: List[RecommendedProduct]
    explanation: str


class RecommendationEvaluationResponse(BaseModel):
    evaluation_k: int
    sample_size_users: int
    mean_precision_at_k: float
    mean_recall_at_k: float
    hit_rate_at_k: float
    ndcg_at_k: Optional[float] = None
    split_method: Optional[str] = None
    model_comparisons: Optional[Dict[str, Dict[str, float]]] = None
    message: Optional[str] = None

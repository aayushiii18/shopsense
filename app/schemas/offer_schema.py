"""
schemas/offer_schema.py — Pydantic schemas for Personalized Offer Strategy & Stock Impact Analysis.
Stage 5 Module 8.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class PersonalizedOfferItem(BaseModel):
    offer_id: str
    target_customer_id: int
    customer_name: str
    target_segment: str  # "Champions / VIP", "At-Risk", "Core Regulars", "New Shopper"
    product_id: int
    product_name: str
    category: str
    original_price: float
    discount_pct: float
    discounted_price: float
    recommendation_pathway: str  # e.g., "Cross-Sell complementary to recent Headphones purchase"
    strategic_objective: str  # "Win-Back Churn Mitigation", "Basket Expansion", "Loyalty Reward"
    rationale: str


class OfferStrategyResponse(BaseModel):
    total_personalized_offers: int
    strategy_timestamp: str
    segment_distribution: Dict[str, int]
    offers: List[PersonalizedOfferItem]
    policy_governance_note: str


class StockImpactRequest(BaseModel):
    product_id: int
    discount_pct: float = Field(..., ge=1.0, le=50.0, description="Proposed discount percentage")
    forecast_horizon_days: int = Field(30, ge=7, le=90, description="Evaluation window in days")
    confirmed_replenishment: int = Field(0, ge=0, description="Confirmed incoming PO units")


class StockImpactResponse(BaseModel):
    product_id: int
    product_name: str
    category: str
    current_stock: int
    confirmed_replenishment: int
    forecast_horizon_days: int
    baseline_demand: float
    discount_pct: float
    price_elasticity: float
    elasticity_source: str  # "VENDOR_SPECIFIC", "CATEGORY_BENCHMARK", "PLATFORM_FALLBACK"
    is_empirically_learned: bool
    projected_promotional_lift: float
    total_projected_demand: float
    safety_stock: int
    projected_ending_stock: float
    status: str  # "APPROVED" or "SUPPRESSED"
    decision_reason: str
    audit_explanation: str


# Aliases
PersonalizedOfferStrategyResponse = OfferStrategyResponse
StockImpactAssessmentRequest = StockImpactRequest
StockImpactAssessmentResponse = StockImpactResponse

"""
schemas/customer_schema.py — Pydantic schemas for customer intelligence endpoints:
RFM Segmentation, Predictive Churn, Cohort Retention, Predictive CLV, and Conversion Funnels.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
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


# ── Stage 5: Churn Prediction Schemas ───────────────────────────────────────

class ChurnContributingFactor(BaseModel):
    feature_name: str
    feature_value: float
    impact_direction: str  # e.g., "Increases Churn Risk" or "Protective / Retention"
    description: str


class CustomerChurnItem(BaseModel):
    customer_id: int
    name: str
    email: str
    churn_probability: float
    risk_category: str  # "HIGH", "MEDIUM", "LOW"
    predicted_churn: int  # 0 or 1
    actual_churn: Optional[int] = None
    recency_days: int
    frequency_obs: int
    monetary_obs: float
    contributing_factors: List[ChurnContributingFactor] = []


class ChurnModelMetrics(BaseModel):
    model_name: str
    observation_window: str
    outcome_window: str
    total_customers: int
    active_count: int
    churned_count: int
    baseline_churn_rate: float
    validation_method: str
    roc_auc_mean: float
    roc_auc_std: float
    precision_mean: float
    recall_mean: float
    f1_mean: float
    pr_auc: float
    confusion_matrix: Dict[str, int]
    comparison_baseline: Dict[str, Any]
    limitations_note: str


class CustomerChurnResponse(BaseModel):
    metrics: ChurnModelMetrics
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    customers: List[CustomerChurnItem]


class SingleCustomerChurnResponse(BaseModel):
    customer_id: int
    name: str
    email: str
    churn_probability: float
    risk_category: str
    predicted_churn: int
    recency_days: int
    frequency_obs: int
    monetary_obs: float
    contributing_factors: List[ChurnContributingFactor]
    model_note: str


# Aliases for flexibility across route naming
ChurnSummaryResponse = CustomerChurnResponse


# ── Stage 5: Cohort Retention Schemas ────────────────────────────────────────

class CohortPeriodRetention(BaseModel):
    period_month: int  # 1 to 12
    activity_month_label: str  # "2024-01", etc.
    active_customers: int
    retention_pct: float


class CohortRetentionItem(BaseModel):
    cohort_label: str  # "2023-06", etc.
    cohort_size: int
    retention_periods: List[CohortPeriodRetention]


class CohortRetentionMatrixResponse(BaseModel):
    cohort_type: str  # "signup_month" or "first_purchase_month"
    total_cohorts: int
    cohorts: List[CohortRetentionItem]
    average_retention_by_period: Dict[int, float]
    methodology_note: str


CohortRetentionResponse = CohortRetentionMatrixResponse


# ── Stage 5: Predictive CLV Schemas ──────────────────────────────────────────

class CustomerCLVItem(BaseModel):
    customer_id: int
    name: str
    historical_spend: float
    order_count: int
    avg_order_value: float
    recency_days: int
    active_probability: float
    predicted_future_orders_12m: float
    predicted_future_spend_12m: float
    total_predicted_clv: float
    clv_tier: str  # "Tier 1: Platinum", "Tier 2: Gold", "Tier 3: Silver", "Tier 4: Bronze"
    clv_lower_bound: float
    clv_upper_bound: float


class CustomerCLVResponse(BaseModel):
    total_customers: int
    aggregate_historical_revenue: float
    aggregate_predicted_12m_future_value: float
    mean_clv: float
    median_clv: float
    clv_tiers_distribution: Dict[str, int]
    customers: List[CustomerCLVItem]
    model_assumptions: str


class SingleCustomerCLVResponse(BaseModel):
    customer_id: int
    name: str
    historical_spend: float
    order_count: int
    predicted_future_spend_12m: float
    total_predicted_clv: float
    clv_tier: str
    uncertainty_bounds: Dict[str, float]
    recommendation_pathway: str


CLVSummaryResponse = CustomerCLVResponse


# ── Stage 5: Conversion Funnel Schemas ───────────────────────────────────────

class FunnelStageItem(BaseModel):
    stage_id: int
    stage_name: str
    event_type: str
    total_events: int
    unique_users: int
    conversion_from_previous_pct: float
    dropoff_from_previous_pct: float
    overall_conversion_pct: float


class ConversionFunnelResponse(BaseModel):
    funnel_name: str
    timeframe: str
    stages: List[FunnelStageItem]
    total_visitors_discovered: int
    total_purchasing_customers: int
    overall_funnel_conversion_pct: float
    data_authenticity_declaration: str

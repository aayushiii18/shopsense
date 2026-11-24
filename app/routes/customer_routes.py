"""
routes/customer_routes.py — FastAPI endpoints for Customer Analytics, Segmentation & Retention Intelligence.

Endpoints:
  GET  /analytics/customers/summary             Marketplace customer KPIs and lifetime value
  GET  /analytics/customers/rfm                 RFM behavioral features per customer
  GET  /analytics/customers/segments            K-Means customer clusters with silhouette validation
  GET  /analytics/customers/churn               Customer churn prediction & ML evaluation metrics
  GET  /analytics/customers/churn/{customer_id} Single customer churn risk score & drivers
  GET  /analytics/customers/cohorts             Signup cohort retention matrix across calendar months
  GET  /analytics/customers/clv                 12-month forward predictive CLV summary & tiers
  GET  /analytics/customers/clv/{customer_id}   Single customer predictive CLV projection
  GET  /analytics/customers/conversion-funnel   Empirical 3-stage conversion funnel
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.dependencies import get_current_user, verify_customer_tenant
from app.models.user import User
from app.services import (
    customer_service,
    revenue_service,
    churn_service,
    cohort_service,
    clv_service,
    funnel_service,
)
from app.schemas.revenue_schema import CustomerMetricsResponse
from app.schemas.customer_schema import (
    ChurnSummaryResponse,
    CustomerChurnResponse,
    SingleCustomerChurnResponse,
    CohortRetentionResponse,
    CLVSummaryResponse,
    CustomerCLVResponse,
    SingleCustomerCLVResponse,
    ConversionFunnelResponse,
)

router = APIRouter(prefix="/analytics/customers", tags=["Customer Analytics"])


@router.get("", response_model=CustomerMetricsResponse, summary="Customer Metrics & Average Spend")
@router.get("/", response_model=CustomerMetricsResponse, include_in_schema=False)
def customer_metrics(db: Session = Depends(get_db)):
    """Returns total registered customer count and average customer spending."""
    return revenue_service.get_customer_metrics(db)


@router.get("/summary", summary="Customer Base Summary & Lifetime Value")
def customer_summary(db: Session = Depends(get_db)):
    """Returns total customers, active count, repeat rates, and average spend."""
    return customer_service.get_customer_summary(db)


@router.get("/rfm", summary="Customer RFM Behavioral Analytics")
def customer_rfm(db: Session = Depends(get_db)):
    """Computes Recency, Frequency, Monetary, and AOV for every registered customer."""
    return customer_service.compute_rfm_metrics(db)


@router.get("/segments", summary="K-Means Customer Segmentation & Silhouette Evaluation")
def customer_segments(
    n_clusters: Optional[int] = Query(None, ge=2, le=6, description="Optional cluster count override"),
    db: Session = Depends(get_db),
):
    """
    Groups customers into behavioral segments using K-Means clustering on standardized RFM features.
    Evaluates cluster cohesion and separation using the Silhouette Score.
    """
    return customer_service.segment_customers(db, n_clusters=n_clusters)


# ── Stage 5 Endpoints: Churn, Cohorts, CLV, Conversion Funnel ─────────────────


@router.get("/churn", response_model=ChurnSummaryResponse, summary="Customer Churn Prediction & Model Metrics")
def customer_churn(db: Session = Depends(get_db)):
    """
    Predicts customer churn probability and risk tier using an L2 regularized logistic model
    trained on Jan–Sep 2024 features against Oct–Dec 2024 retention outcomes.
    Evaluated with 5-fold stratified cross-validation and feature explainability.
    """
    return churn_service.predict_customer_churn(db)


@router.get("/churn/{customer_id}", response_model=SingleCustomerChurnResponse, summary="Single Customer Churn Risk")
def single_customer_churn(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns individual churn prediction and top risk drivers for a specific customer."""
    verify_customer_tenant(current_user, customer_id)
    res = churn_service.get_single_customer_churn(db, customer_id=customer_id)
    if not res:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
    return res


@router.get("/cohorts", response_model=CohortRetentionResponse, summary="Customer Signup Cohort Retention Matrix")
def customer_cohorts(db: Session = Depends(get_db)):
    """
    Computes monthly cohort retention percentages across calendar months for customer signup cohorts.
    """
    return cohort_service.compute_cohort_retention(db)


@router.get("/clv", response_model=CLVSummaryResponse, summary="Predictive Customer Lifetime Value (CLV)")
def customer_clv(db: Session = Depends(get_db)):
    """
    Computes 12-month forward predictive CLV combining Bayesian shrinkage AOV,
    inactivity decay, and gross margin, strictly separating historical spend from forward projections.
    """
    return clv_service.compute_predictive_clv(db)


@router.get("/clv/{customer_id}", response_model=SingleCustomerCLVResponse, summary="Single Customer Predictive CLV")
def single_customer_clv(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns individual 12-month forward predictive CLV, historical spend, and tier."""
    verify_customer_tenant(current_user, customer_id)
    res = clv_service.get_single_customer_clv(db, customer_id=customer_id)
    if not res:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
    return res


@router.get("/conversion-funnel", response_model=ConversionFunnelResponse, summary="Empirical Conversion Funnel")
def customer_conversion_funnel(db: Session = Depends(get_db)):
    """
    Computes empirical conversion funnel (View -> Add to Cart -> Purchase)
    from recorded customer behavioral interaction events.
    """
    return funnel_service.compute_conversion_funnel(db)

"""
routes/customer_routes.py — FastAPI endpoints for Customer Analytics & Segmentation.

Endpoints:
  GET  /analytics/customers/summary     Marketplace customer KPIs and lifetime value
  GET  /analytics/customers/rfm         RFM behavioral features per customer
  GET  /analytics/customers/segments    K-Means customer clusters with silhouette validation
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import customer_service

router = APIRouter(prefix="/analytics/customers", tags=["Customer Analytics"])


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

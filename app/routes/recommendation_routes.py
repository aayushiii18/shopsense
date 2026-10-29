"""
routes/recommendation_routes.py — FastAPI endpoints for Recommendation Engine.

Endpoints:
  GET /recommendations/customer/{id}   Personalized Top-N recommendations for customer
  GET /recommendations/popular         Popular products for cold-start recommendations
  GET /recommendations/evaluation      Offline Precision@K & Recall@K model evaluation
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import recommendation_service

router = APIRouter(prefix="/recommendations", tags=["Recommendation Engine"])


@router.get("/customer/{customer_id}", summary="Personalized Top-N Product Recommendations")
def get_customer_recommendations(
    customer_id: int,
    top_n: int = Query(5, ge=1, le=20, description="Number of recommendations to return"),
    exclude_purchased: bool = Query(True, description="Filter out products already interacted with"),
    db: Session = Depends(get_db),
):
    """
    Returns personalized product recommendations for a customer using
    Item-Based Collaborative Filtering. Falls back gracefully to top sellers.
    """
    try:
        return recommendation_service.get_personalized_recommendations(
            db, customer_id=customer_id, top_n=top_n, exclude_purchased=exclude_purchased
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/popular", summary="Cold-Start Popularity Recommendations")
def get_popular(
    top_n: int = Query(5, ge=1, le=20, description="Number of top products"),
    db: Session = Depends(get_db),
):
    """Returns top-selling products across the platform."""
    return recommendation_service.get_popular_products(db, top_n=top_n)


@router.get("/evaluation", summary="Offline Recommendation Evaluation (Precision@K, Recall@K)")
def evaluate_engine(
    k: int = Query(5, ge=1, le=10, description="Evaluation top-K parameter"),
    db: Session = Depends(get_db),
):
    """
    Runs offline evaluation on a chronological 80/20 held-out interaction split,
    reporting Precision@K, Recall@K, and Hit Rate.
    """
    return recommendation_service.evaluate_recommendation_engine(db, k=k)

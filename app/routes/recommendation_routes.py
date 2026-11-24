"""
routes/recommendation_routes.py — FastAPI endpoints for Recommendation Engine.

Endpoints:
  GET /recommendations/customer/{id}        Personalized Top-N recommendations for customer (CF)
  GET /recommendations/popular              Popular products for cold-start recommendations
  GET /recommendations/evaluation           Offline Precision@K & Recall@K model evaluation
  GET /recommendations/hybrid/evaluation    Chronological Holdout Model Comparison (Hybrid vs CF vs Content vs Pop)
  GET /recommendations/hybrid/{customer_id} Hybrid Recommendation (CF + TF-IDF Content + Safety Stock Check)
  GET /recommend/{customer_id}              Top Recommended Product for Customer (Legacy/Single)
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import recommendation_service, hybrid_recommender
from app.schemas.revenue_schema import SingleRecommendationResponse
from app.schemas.recommendation_schema import (
    HybridRecommendationResponse,
    RecommendationEvaluationResponse,
)
from app.core.dependencies import get_current_user, verify_customer_tenant
from app.models.user import User

router = APIRouter(prefix="/recommendations", tags=["Recommendation API", "Recommendation Engine"])
recommend_router = APIRouter(tags=["Recommendation API", "Recommendation Engine"])


@recommend_router.get(
    "/recommend/{customer_id}",
    response_model=SingleRecommendationResponse,
    summary="Top Recommended Product for Customer",
)
def recommend(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the customer's dynamically generated recommended product
    using Item-Based Collaborative Filtering (with popularity fallback).
    Enforces customer data ownership verification.
    Returns 404 if customer is not found.
    """
    verify_customer_tenant(current_user, customer_id)
    try:
        res = recommendation_service.get_personalized_recommendations(
            db, customer_id=customer_id, top_n=1, exclude_purchased=False
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    recs = res.get("recommendations", [])
    if recs:
        top_rec = recs[0]
        return {
            "customer": customer_id,
            "recommended_product": top_rec["product_name"],
            "customer_name": res.get("customer_name"),
            "category": top_rec.get("category"),
            "score": top_rec.get("score"),
            "is_personalized": res.get("is_personalized", True),
        }
    else:
        pop = recommendation_service.get_popular_products(db, top_n=1)
        top_name = pop[0]["product_name"] if pop else "Standard Catalog Item"
        return {
            "customer": customer_id,
            "recommended_product": top_name,
            "customer_name": res.get("customer_name"),
            "category": "General",
            "score": 1.0,
            "is_personalized": False,
        }


@router.get("/customer/{customer_id}", summary="Personalized Top-N Product Recommendations")
def get_customer_recommendations(
    customer_id: int,
    top_n: int = Query(5, ge=1, le=20, description="Number of recommendations to return"),
    exclude_purchased: bool = Query(True, description="Filter out products already interacted with"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns personalized product recommendations for a customer using
    Item-Based Collaborative Filtering. Falls back gracefully to top sellers.
    Enforces customer ownership verification.
    """
    verify_customer_tenant(current_user, customer_id)
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


# ── Stage 5 Hybrid Recommendation Endpoints ───────────────────────────────────


@router.get(
    "/hybrid/evaluation",
    response_model=RecommendationEvaluationResponse,
    summary="Chronological Holdout Hybrid & Baseline Recommendation Evaluation",
)
def evaluate_hybrid_models(
    k: int = Query(5, ge=1, le=10, description="Evaluation top-K parameter"),
    holdout_date: str = Query("2024-10-01", description="Holdout cutoff date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """
    Evaluates Hybrid, Collaborative Filtering, Content-Based, and Popularity Fallback
    models on chronological holdout data (Oct–Dec 2024) across Precision@K, Recall@K,
    and NDCG@K.
    """
    return hybrid_recommender.evaluate_recommendation_models(db, k=k, holdout_date=holdout_date)


@router.get(
    "/hybrid/{customer_id}",
    response_model=HybridRecommendationResponse,
    summary="Personalized Hybrid Product Recommendations (CF + TF-IDF Content)",
)
def get_hybrid_recommendations(
    customer_id: int,
    top_n: int = Query(5, ge=1, le=20, description="Number of recommendations"),
    alpha: float = Query(0.6, ge=0.0, le=1.0, description="Collaborative Filtering weight (0=Content, 1=CF)"),
    exclude_interacted: bool = Query(True, description="Exclude items customer has already bought or viewed"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generates personalized recommendations combining Item-Based Collaborative Filtering
    and TF-IDF Content-Based filtering, with strictly verified stock availability.
    Enforces customer ownership verification.
    """
    verify_customer_tenant(current_user, customer_id)
    try:
        return hybrid_recommender.get_hybrid_recommendations(
            db,
            customer_id=customer_id,
            top_n=top_n,
            alpha=alpha,
            exclude_interacted=exclude_interacted,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

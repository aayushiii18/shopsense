"""
routes/offer_routes.py — FastAPI endpoints for Personalized Offer Strategy & Stock Impact Safety Guard.

Endpoints:
  GET  /offers/strategy                     Personalized offer strategies per customer segment
  POST /offers/stock-impact                 Simulate promotional stock impact and safety stock compliance
  GET  /offers/stock-impact/{product_id}    Single product promotional stock impact assessment
  GET  /offers/elasticity/{product_id}      Resolve price elasticity hierarchy for product
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import offer_service
from app.models.product import Product
from app.schemas.offer_schema import (
    OfferStrategyResponse,
    StockImpactRequest,
    StockImpactResponse,
)

router = APIRouter(prefix="/offers", tags=["Offer Strategy & Stock Impact"])


@router.get(
    "/strategy",
    response_model=OfferStrategyResponse,
    summary="Personalized Promotional Offer Strategy",
)
def get_offer_strategy(
    limit: int = Query(20, ge=1, le=100, description="Max number of candidate offers to generate"),
    db: Session = Depends(get_db),
):
    """
    Generates personalized promotional offers mapped to customer RFM segments,
    churn risks, and product affinity, checking stock safety before proposing discounts.
    """
    return offer_service.generate_personalized_offer_strategy(db, limit=limit)


@router.post(
    "/stock-impact",
    response_model=StockImpactResponse,
    summary="Simulate Promotional Stock Impact & Safety Stock Compliance",
)
def simulate_stock_impact(
    payload: StockImpactRequest,
    db: Session = Depends(get_db),
):
    """
    Evaluates promotional demand lift and post-campaign stock feasibility:
      Ending Stock = Current Stock + Replenishment - Baseline Demand - Lift.
    Strictly suppresses offers when Ending Stock drops below dynamic Safety Stock (reorder_level).
    """
    try:
        return offer_service.evaluate_stock_impact_safety(
            db,
            product_id=payload.product_id,
            discount_pct=payload.discount_pct,
            horizon_days=payload.forecast_horizon_days,
            confirmed_replenishment=payload.confirmed_replenishment,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/stock-impact/{product_id}",
    response_model=StockImpactResponse,
    summary="Single Product Stock Impact Assessment",
)
def get_product_stock_impact(
    product_id: int,
    discount_pct: float = Query(10.0, ge=1.0, le=50.0, description="Proposed discount percentage"),
    horizon_days: int = Query(30, ge=7, le=90, description="Evaluation window in days"),
    confirmed_replenishment: int = Query(0, ge=0, description="Confirmed incoming PO units"),
    db: Session = Depends(get_db),
):
    """
    Evaluates stock safety for an individual product under proposed discount parameters.
    """
    return offer_service.evaluate_stock_impact_safety(
        db,
        product_id=product_id,
        discount_pct=discount_pct,
        horizon_days=horizon_days,
        confirmed_replenishment=confirmed_replenishment,
    )


@router.get(
    "/elasticity/{product_id}",
    summary="Resolve Hierarchical Price Elasticity for Product",
)
def get_product_elasticity(product_id: int, db: Session = Depends(get_db)):
    """
    Resolves price elasticity through the 3-tier hierarchy:
      1. Vendor-Specific (requires >= 30 historical price changes)
      2. Category-Level Benchmark
      3. Platform Fallback (|epsilon| = 1.5)
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
    return offer_service.resolve_price_elasticity(db, product)

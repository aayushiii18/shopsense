"""
routes/inventory_routes.py — FastAPI endpoints for Product & Inventory Analytics.

Endpoints:
  GET  /analytics/inventory/status          Current stock levels, valuation, and status
  GET  /analytics/inventory/movements       Recent stock movement audit trail
  POST /inventory/movements                 Record a new stock movement
  GET  /analytics/inventory/turnover        Turnover ratios, DSI, and velocity categories
  GET  /analytics/inventory/low-stock       Low-stock alerts and depletion days
  GET  /analytics/inventory/replenishment   Dynamic replenishment recommendations (ROP, SS)
  GET  /analytics/inventory/forecast/{id}   Demand forecasting with seasonal holdout validation
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.inventory_schema import StockMovementCreate
from app.services import inventory_service

router = APIRouter(prefix="/analytics/inventory", tags=["Inventory Analytics"])
movement_router = APIRouter(prefix="/inventory", tags=["Inventory Operations"])


@router.get("/status", summary="Real-time Inventory Status & Valuation")
def inventory_status(db: Session = Depends(get_db)):
    """Returns catalog inventory stock levels, valuations, and status indicators."""
    return inventory_service.get_inventory_status(db)


@router.get("/movements", summary="Stock Movement Audit Trail")
def list_movements(
    product_id: Optional[int] = Query(None, description="Filter by product ID"),
    movement_type: Optional[str] = Query(None, description="Filter by movement type"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Returns historical stock movements."""
    return inventory_service.get_stock_movements(
        db, product_id=product_id, movement_type=movement_type, limit=limit
    )


@movement_router.post("/movements", summary="Record a Stock Movement", status_code=status.HTTP_201_CREATED)
def create_movement(payload: StockMovementCreate, db: Session = Depends(get_db)):
    """
    Records an inventory stock movement (RESTOCK, SALE, ADJUSTMENT, TRANSFER, RETURN)
    and updates the active product inventory accordingly.
    """
    try:
        movement = inventory_service.record_stock_movement(
            db,
            product_id=payload.product_id,
            movement_type=payload.movement_type,
            quantity=payload.quantity,
            source_warehouse=payload.source_warehouse,
            target_warehouse=payload.target_warehouse,
            reference_id=payload.reference_id,
            notes=payload.notes,
        )
        return {
            "movement_id": movement.movement_id,
            "product_id": movement.product_id,
            "movement_type": movement.movement_type,
            "quantity": movement.quantity,
            "source_warehouse": movement.source_warehouse,
            "target_warehouse": movement.target_warehouse,
            "reference_id": movement.reference_id,
            "notes": movement.notes,
            "created_at": movement.created_at.isoformat() if movement.created_at else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/turnover", summary="Inventory Turnover & Days Sales of Inventory")
def inventory_turnover(
    days: int = Query(365, ge=7, le=1095, description="Lookback window in days"),
    db: Session = Depends(get_db),
):
    """
    Calculates inventory turnover ratios, DSI, and velocity classifications
    (Fast-moving, Normal, Slow-moving, Dead stock).
    """
    return inventory_service.calculate_inventory_turnover(db, days=days)


@router.get("/low-stock", summary="Low-Stock Alerts & Depletion Projections")
def low_stock_alerts(db: Session = Depends(get_db)):
    """Returns products at or below their reorder threshold with days until stockout."""
    return inventory_service.get_low_stock_alerts(db)


@router.get("/replenishment", summary="Replenishment Recommendations & Safety Stock")
def replenishment_recommendations(
    lead_time_days: int = Query(5, ge=1, le=60, description="Supplier lead time in days"),
    service_level: float = Query(0.95, ge=0.5, le=0.999, description="Desired service level factor"),
    db: Session = Depends(get_db),
):
    """
    Calculates dynamic Reorder Points (ROP), Safety Stock (SS), and Recommended Order Quantities.
    """
    # Map service level to z-score
    z_map = {0.90: 1.28, 0.95: 1.65, 0.98: 2.05, 0.99: 2.33}
    service_factor = z_map.get(round(service_level, 2), 1.65)

    return inventory_service.get_replenishment_recommendations(
        db, lead_time_days=lead_time_days, service_factor=service_factor
    )


@router.get("/forecast/{product_id}", summary="Time-Series Demand Forecasting with Seasonality")
def demand_forecast(
    product_id: int,
    forecast_days: int = Query(14, ge=1, le=90, description="Days to forecast ahead"),
    db: Session = Depends(get_db),
):
    """
    Projects daily demand using seasonal indicators and linear trend.
    Evaluates historical accuracy on a chronological 80/20 test holdout (MAE, RMSE, WAPE).
    """
    try:
        return inventory_service.forecast_product_demand(
            db, product_id=product_id, forecast_days=forecast_days
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

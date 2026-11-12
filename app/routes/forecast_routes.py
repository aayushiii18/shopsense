"""
routes/forecast_routes.py — FastAPI endpoints for Inventory Demand Forecasting.
Milestone 3 Module 1.

Endpoints:
  GET /forecast/{month}   Predict monthly inventory demand units
"""

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import inventory_service
from app.schemas.revenue_schema import ForecastResponse

router = APIRouter(tags=["Demand Forecasting"])


@router.get(
    "/forecast/{month}",
    response_model=ForecastResponse,
    summary="Predict Monthly Inventory Demand",
)
def forecast(
    month: int = Path(..., description="Month number to forecast (1-12 or future month up to 24)"),
    db: Session = Depends(get_db),
):
    """
    Returns monthly inventory demand units predicted by the trained RandomForest forecasting model.
    Validates month parameter (must be between 1 and 24).
    """
    if month < 1 or month > 24:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid month {month}: must be between 1 and 24.",
        )
    try:
        return inventory_service.predict_monthly_demand(month=month, db=db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

"""
routes/catalog_routes.py — FastAPI endpoints for Catalog Normalization & Taxonomy Aggregation.

Endpoints:
  GET /catalog/normalize               Catalog-wide taxonomy normalization, attribute extraction & health audit
  GET /catalog/normalize/{product_id}  Single product normalized attribute view & confidence
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import catalog_normalizer
from app.schemas.catalog_schema import (
    CatalogNormalizationSummaryResponse,
    NormalizedProductResponse,
)

router = APIRouter(prefix="/catalog", tags=["Catalog Normalization"])


@router.get(
    "/normalize",
    response_model=CatalogNormalizationSummaryResponse,
    summary="Catalog-Wide Normalization & Attribute Health Audit",
)
def normalize_catalog(db: Session = Depends(get_db)):
    """
    Standardizes vendor-submitted product titles into clean canonical names,
    hierarchical category taxonomies (Parent -> Leaf), inferred brands, extracted
    units/specifications, price outlier validations, and duplicate candidate detection.
    Non-destructive: original product records are strictly preserved.
    """
    return catalog_normalizer.normalize_catalog(db)


@router.get(
    "/normalize/{product_id}",
    response_model=NormalizedProductResponse,
    summary="Single Product Normalized Attributes",
)
def normalize_single_product(product_id: int, db: Session = Depends(get_db)):
    """
    Returns normalized taxonomy, extracted unit, inferred brand, and price sanity
    for a specific catalog product.
    """
    res = catalog_normalizer.normalize_single_product(db, product_id=product_id)
    if not res:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
    return res

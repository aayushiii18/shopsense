"""
schemas/catalog_schema.py — Pydantic schemas for the Catalog Normalization Engine.
Stage 5 Module 5.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class NormalizedMeasurement(BaseModel):
    has_measurement: bool = False
    raw_text: Optional[str] = None
    normalized_value: Optional[float] = None
    normalized_unit: Optional[str] = None  # "kg", "g", "inches", "pack", etc.
    unit_type: Optional[str] = None  # "weight", "dimension", "pack_count", etc.


class NormalizedCatalogItem(BaseModel):
    product_id: int
    original_name: str
    normalized_name: str
    original_category: Optional[str] = None
    normalized_category: str
    parent_category: str
    vendor_id: int
    inferred_brand: str
    price: float
    cost_price: Optional[float] = None
    markup_pct: Optional[float] = None
    measurement: NormalizedMeasurement
    quality_score: float = Field(..., ge=0.0, le=100.0)
    flags: List[str] = []
    is_duplicate: bool = False
    duplicate_of_id: Optional[int] = None


class CatalogNormalizationSummaryResponse(BaseModel):
    total_products_inspected: int
    categories_normalized_count: int
    units_extracted_count: int
    brands_standardized_count: int
    duplicate_candidates_found: int
    average_attribute_quality_score: float
    taxonomy_mapping: Dict[str, str]
    products: List[NormalizedCatalogItem]
    normalization_policy_note: str


# Aliases
NormalizedProductResponse = NormalizedCatalogItem

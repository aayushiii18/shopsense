"""
routes/product_routes.py — FastAPI endpoints for product catalog management.

POST /products/       Register a new product (must reference an existing vendor)
GET  /products/       List all products (paginated, optional vendor filter)
GET  /products/{id}   Get a single product by ID
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.product import Product
from app.models.vendor import Vendor
from app.schemas.product_schema import ProductCreate, ProductResponse

router = APIRouter(prefix="/products", tags=["Products"])


@router.post(
    "/",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new product",
)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    """
    Add a product to the catalog.

    - vendor_id must reference an existing vendor (returns 404 if not found).
    - price must be > 0 (enforced by Pydantic schema).
    """
    vendor = db.query(Vendor).filter(Vendor.id == payload.vendor_id).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor with id={payload.vendor_id} not found.",
        )

    product = Product(
        name=payload.name,
        description=payload.description,
        price=payload.price,
        category=payload.category,
        vendor_id=payload.vendor_id,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get(
    "/",
    response_model=list[ProductResponse],
    summary="List all products",
)
def list_products(
    skip: int = 0,
    limit: int = 100,
    vendor_id: int | None = Query(default=None, description="Filter by vendor ID"),
    db: Session = Depends(get_db),
):
    """Return a paginated list of products, optionally filtered by vendor."""
    if limit > 500:
        raise HTTPException(status_code=400, detail="limit cannot exceed 500.")
    query = db.query(Product)
    if vendor_id is not None:
        query = query.filter(Product.vendor_id == vendor_id)
    return query.offset(skip).limit(limit).all()


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Get product by ID",
)
def get_product(product_id: int, db: Session = Depends(get_db)):
    """Return a single product record, or 404 if not found."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id={product_id} not found.",
        )
    return product

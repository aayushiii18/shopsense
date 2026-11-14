"""
routes/product_routes.py — FastAPI endpoints for product catalog management.

POST /products/       Register a new product (validates active vendor and optional cost_price)
GET  /products/       List all products (paginated, optional vendor filter)
GET  /products/{id}   Get a single product by ID
PUT  /products/{id}   Update an existing product
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.product import Product
from app.models.vendor import Vendor
from app.schemas.product_schema import ProductCreate, ProductUpdate, ProductResponse
from app.services import vendor_service

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
    - vendor must not be in an inactive/suspended/terminated state (returns 403).
    - price must be > 0.
    - cost_price is optional (nullable) for verified COGS accounting.
    """
    vendor = db.query(Vendor).filter(Vendor.id == payload.vendor_id).first()
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor with id={payload.vendor_id} not found.",
        )

    # Enforce operational vendor status restriction
    vendor_service.verify_vendor_can_list_products(vendor)

    product = Product(
        name=payload.name,
        description=payload.description,
        price=payload.price,
        cost_price=payload.cost_price,
        category=payload.category,
        parent_category=payload.parent_category,
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


@router.put(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Update product details",
)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)):
    """Update an existing product's name, price, cost_price, description, category, or vendor."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id={product_id} not found.",
        )
    if payload.vendor_id is not None:
        vendor = db.query(Vendor).filter(Vendor.id == payload.vendor_id).first()
        if not vendor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Vendor with id={payload.vendor_id} not found.",
            )
        vendor_service.verify_vendor_can_list_products(vendor)
        product.vendor_id = payload.vendor_id

    if payload.name:
        product.name = payload.name
    if payload.description is not None:
        product.description = payload.description
    if payload.price is not None:
        product.price = payload.price
    if payload.cost_price is not None:
        product.cost_price = payload.cost_price
    if payload.category is not None:
        product.category = payload.category
    if payload.parent_category is not None:
        product.parent_category = payload.parent_category

    db.commit()
    db.refresh(product)
    return product

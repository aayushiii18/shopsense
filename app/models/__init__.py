# app/models/__init__.py
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.transaction import Transaction
from app.models.customer import Customer
from app.models.stock_movement import StockMovement
from app.models.customer_interaction import CustomerInteraction

__all__ = [
    "Vendor",
    "Product",
    "Inventory",
    "Transaction",
    "Customer",
    "StockMovement",
    "CustomerInteraction",
]

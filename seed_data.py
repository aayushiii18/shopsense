"""
seed_data.py — Idempotent database seeder for StockPilot.

Reads CSV files from the data/ directory and safely ingests them into the
PostgreSQL database configured in .env.
Safe to run multiple times without duplicating records.

Usage:
    python seed_data.py
"""

import os
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import engine, SessionLocal
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.models.stock_movement import StockMovement
from app.models.customer_interaction import CustomerInteraction

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def seed_vendors(db: Session):
    csv_path = os.path.join(DATA_DIR, "vendors.csv")
    if not os.path.exists(csv_path):
        return
    df = pd.read_csv(csv_path)
    for _, row in df.iterrows():
        existing = db.query(Vendor).filter_by(id=int(row["id"])).first()
        if not existing:
            v = Vendor(
                id=int(row["id"]),
                name=row["name"],
                email=row["email"],
                phone=row["phone"],
                address=row.get("address"),
            )
            db.add(v)
    db.commit()
    # Reset postgres sequence
    db.execute(text("SELECT setval(pg_get_serial_sequence('vendors', 'id'), coalesce(max(id), 1)) FROM vendors;"))
    db.commit()
    print("Vendors seeded.")


def seed_products(db: Session):
    csv_path = os.path.join(DATA_DIR, "products.csv")
    if not os.path.exists(csv_path):
        return
    df = pd.read_csv(csv_path)
    for _, row in df.iterrows():
        existing = db.query(Product).filter_by(id=int(row["id"])).first()
        if not existing:
            p = Product(
                id=int(row["id"]),
                name=row["name"],
                price=float(row["price"]),
                category=row.get("category"),
                parent_category=row.get("parent_category"),
                vendor_id=int(row["vendor_id"]),
            )
            db.add(p)
    db.commit()
    db.execute(text("SELECT setval(pg_get_serial_sequence('products', 'id'), coalesce(max(id), 1)) FROM products;"))
    db.commit()
    print("Products seeded.")


def seed_inventory(db: Session):
    csv_path = os.path.join(DATA_DIR, "inventory.csv")
    if not os.path.exists(csv_path):
        return
    df = pd.read_csv(csv_path)
    for _, row in df.iterrows():
        existing = db.query(Inventory).filter_by(product_id=int(row["product_id"])).first()
        if not existing:
            inv = Inventory(
                inventory_id=int(row["inventory_id"]),
                product_id=int(row["product_id"]),
                current_stock=int(row["current_stock"]),
                warehouse=row.get("warehouse", "Main Warehouse"),
                reorder_level=int(row.get("reorder_level", 10)),
            )
            db.add(inv)
        else:
            existing.current_stock = int(row["current_stock"])
            existing.reorder_level = int(row.get("reorder_level", existing.reorder_level))
    db.commit()
    db.execute(text("SELECT setval(pg_get_serial_sequence('inventory', 'inventory_id'), coalesce(max(inventory_id), 1)) FROM inventory;"))
    db.commit()
    print("Inventory seeded.")


def seed_customers(db: Session):
    csv_path = os.path.join(DATA_DIR, "customers.csv")
    if not os.path.exists(csv_path):
        return
    df = pd.read_csv(csv_path)
    for _, row in df.iterrows():
        existing = db.query(Customer).filter_by(customer_id=int(row["customer_id"])).first()
        if not existing:
            c = Customer(
                customer_id=int(row["customer_id"]),
                name=row["name"],
                email=row["email"],
                city=row.get("city"),
                region=row.get("region"),
                signup_date=datetime.strptime(row["signup_date"], "%Y-%m-%d %H:%M:%S"),
            )
            db.add(c)
    db.commit()
    db.execute(text("SELECT setval(pg_get_serial_sequence('customers', 'customer_id'), coalesce(max(customer_id), 1)) FROM customers;"))
    db.commit()
    print("Customers seeded.")


def seed_transactions(db: Session):
    csv_path = os.path.join(DATA_DIR, "transactions.csv")
    if not os.path.exists(csv_path):
        return
    df = pd.read_csv(csv_path)
    current_count = db.query(Transaction).count()
    if current_count >= len(df):
        print("Transactions already seeded.")
        return

    # Ingest rows in batch
    for _, row in df.iterrows():
        existing = db.query(Transaction).filter_by(transaction_id=int(row["transaction_id"])).first()
        if not existing:
            txn = Transaction(
                transaction_id=int(row["transaction_id"]),
                product_id=int(row["product_id"]),
                vendor_id=int(row["vendor_id"]),
                customer_id=int(row["customer_id"]) if pd.notna(row.get("customer_id")) else None,
                quantity=int(row["quantity"]),
                unit_price=float(row["unit_price"]),
                amount=float(row["amount"]),
                transaction_date=datetime.strptime(str(row["transaction_date"]), "%Y-%m-%d %H:%M:%S")
                if " " in str(row["transaction_date"])
                else datetime.strptime(str(row["transaction_date"]), "%Y-%m-%d"),
            )
            db.add(txn)
    db.commit()
    db.execute(text("SELECT setval(pg_get_serial_sequence('transactions', 'transaction_id'), coalesce(max(transaction_id), 1)) FROM transactions;"))
    db.commit()
    print("Transactions seeded.")


def seed_stock_movements(db: Session):
    csv_path = os.path.join(DATA_DIR, "stock_movements.csv")
    if not os.path.exists(csv_path):
        return
    df = pd.read_csv(csv_path)
    current_count = db.query(StockMovement).count()
    if current_count >= len(df):
        print("Stock movements already seeded.")
        return

    for _, row in df.iterrows():
        existing = db.query(StockMovement).filter_by(movement_id=int(row["movement_id"])).first()
        if not existing:
            sm = StockMovement(
                movement_id=int(row["movement_id"]),
                product_id=int(row["product_id"]),
                movement_type=row["movement_type"],
                quantity=int(row["quantity"]),
                source_warehouse=row.get("source_warehouse") if pd.notna(row.get("source_warehouse")) else None,
                target_warehouse=row.get("target_warehouse") if pd.notna(row.get("target_warehouse")) else None,
                reference_id=int(row["reference_id"]) if pd.notna(row.get("reference_id")) else None,
                notes=row.get("notes") if pd.notna(row.get("notes")) else None,
                created_at=datetime.strptime(str(row["created_at"]), "%Y-%m-%d %H:%M:%S"),
            )
            db.add(sm)
    db.commit()
    db.execute(text("SELECT setval(pg_get_serial_sequence('stock_movements', 'movement_id'), coalesce(max(movement_id), 1)) FROM stock_movements;"))
    db.commit()
    print("Stock movements seeded.")


def seed_customer_interactions(db: Session):
    csv_path = os.path.join(DATA_DIR, "customer_interactions.csv")
    if not os.path.exists(csv_path):
        return
    df = pd.read_csv(csv_path)
    current_count = db.query(CustomerInteraction).count()
    if current_count >= len(df):
        print("Customer interactions already seeded.")
        return

    for _, row in df.iterrows():
        existing = db.query(CustomerInteraction).filter_by(interaction_id=int(row["interaction_id"])).first()
        if not existing:
            ci = CustomerInteraction(
                interaction_id=int(row["interaction_id"]),
                customer_id=int(row["customer_id"]),
                product_id=int(row["product_id"]),
                interaction_type=row["interaction_type"],
                interaction_weight=float(row["interaction_weight"]),
                interaction_date=datetime.strptime(str(row["interaction_date"]), "%Y-%m-%d %H:%M:%S"),
            )
            db.add(ci)
    db.commit()
    db.execute(text("SELECT setval(pg_get_serial_sequence('customer_interactions', 'interaction_id'), coalesce(max(interaction_id), 1)) FROM customer_interactions;"))
    db.commit()
    print("Customer interactions seeded.")


def main():
    print("Starting StockPilot idempotent data ingestion...")
    db = SessionLocal()
    try:
        seed_vendors(db)
        seed_products(db)
        seed_inventory(db)
        seed_customers(db)
        seed_transactions(db)
        seed_stock_movements(db)
        seed_customer_interactions(db)
        print("All tables successfully seeded and verified!")
    finally:
        db.close()


if __name__ == "__main__":
    main()

"""
tests/test_inventory.py — Tests for Inventory and Transaction model integrity and constraints.

Covers:
  - Inventory record creation with all required fields
  - Inventory default values (warehouse, reorder_level, current_stock)
  - Inventory current_stock non-negative check constraint
  - Inventory reorder_level non-negative check constraint
  - One-to-one constraint: duplicate product_id in inventory raises IntegrityError
  - Transaction creation with transaction_id, quantity, unit_price, amount
  - Transaction amount positive check constraint
  - Transaction total_price synonym backwards-compatibility
"""

import pytest
from sqlalchemy.exc import IntegrityError
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.transaction import Transaction


def _create_vendor_and_product(db_session):
    v = Vendor(name="Inventory Vendor", email="inv_vendor@example.com", phone="+91-9123456789")
    db_session.add(v)
    db_session.flush()
    p = Product(name="Inventory Product", price=499.00, vendor_id=v.id)
    db_session.add(p)
    db_session.flush()
    return v, p


def test_create_inventory_with_defaults(db_session):
    _, p = _create_vendor_and_product(db_session)
    inv = Inventory(product_id=p.id)
    db_session.add(inv)
    db_session.commit()

    assert inv.inventory_id is not None
    assert inv.product_id == p.id
    assert inv.current_stock == 0
    assert inv.warehouse == "Main Warehouse"
    assert inv.reorder_level == 10
    assert inv.updated_at is not None


def test_create_inventory_custom_values(db_session):
    _, p = _create_vendor_and_product(db_session)
    inv = Inventory(
        product_id=p.id,
        current_stock=150,
        warehouse="Warehouse North - Delhi",
        reorder_level=25,
    )
    db_session.add(inv)
    db_session.commit()

    assert inv.inventory_id is not None
    assert inv.current_stock == 150
    assert inv.warehouse == "Warehouse North - Delhi"
    assert inv.reorder_level == 25


def test_inventory_negative_stock_rejected(db_session):
    _, p = _create_vendor_and_product(db_session)
    inv = Inventory(product_id=p.id, current_stock=-5)
    db_session.add(inv)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_inventory_negative_reorder_level_rejected(db_session):
    _, p = _create_vendor_and_product(db_session)
    inv = Inventory(product_id=p.id, current_stock=10, reorder_level=-1)
    db_session.add(inv)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_inventory_one_to_one_unique_product(db_session):
    _, p = _create_vendor_and_product(db_session)
    inv1 = Inventory(product_id=p.id, current_stock=50)
    db_session.add(inv1)
    db_session.commit()

    # Second inventory for same product must be rejected by unique constraint
    inv2 = Inventory(product_id=p.id, current_stock=75)
    db_session.add(inv2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_transaction_model_fields_and_synonym(db_session):
    v, p = _create_vendor_and_product(db_session)
    txn = Transaction(
        product_id=p.id,
        vendor_id=v.id,
        quantity=5,
        unit_price=499.00,
        amount=2495.00,
    )
    db_session.add(txn)
    db_session.commit()

    assert txn.transaction_id is not None
    assert txn.quantity == 5
    assert txn.unit_price == 499.00
    assert txn.amount == 2495.00
    # Test synonym compatibility
    assert txn.total_price == 2495.00


def test_transaction_negative_amount_rejected(db_session):
    v, p = _create_vendor_and_product(db_session)
    txn = Transaction(
        product_id=p.id,
        vendor_id=v.id,
        quantity=2,
        unit_price=100.0,
        amount=-200.0,
    )
    db_session.add(txn)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

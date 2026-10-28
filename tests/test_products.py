"""
tests/test_products.py — Tests for product catalog registration and validation.

Covers:
  - Successful product creation
  - Non-existent vendor_id rejection (HTTP 404)
  - Invalid price (zero, negative) rejection (HTTP 422)
  - Blank product name rejection (HTTP 422)
  - List products (all and filtered by vendor)
  - Get product by ID
  - 404 for nonexistent product
"""

import pytest


VALID_VENDOR = {
    "name": "GadgetHub",
    "email": "gadgethub@example.com",
    "phone": "+91-9000000001",
}


def _create_vendor(client):
    resp = client.post("/vendors/", json=VALID_VENDOR)
    assert resp.status_code == 201
    return resp.json()["id"]


def _valid_product(vendor_id: int):
    return {
        "name": "Wireless Mouse",
        "description": "Ergonomic 2.4GHz wireless mouse",
        "price": 699.00,
        "category": "Electronics",
        "vendor_id": vendor_id,
    }


# ── Registration success ──────────────────────────────────────────────────────

def test_create_product_success(client):
    vendor_id = _create_vendor(client)
    resp = client.post("/products/", json=_valid_product(vendor_id))
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Wireless Mouse"
    assert data["price"] == 699.00
    assert data["vendor_id"] == vendor_id
    assert "id" in data


def test_create_product_without_optional_fields(client):
    vendor_id = _create_vendor(client)
    payload = {"name": "Basic Item", "price": 100.0, "vendor_id": vendor_id}
    resp = client.post("/products/", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["description"] is None
    assert data["category"] is None


# ── Vendor existence check ────────────────────────────────────────────────────

def test_product_with_nonexistent_vendor_rejected(client):
    payload = _valid_product(99999)  # vendor doesn't exist
    resp = client.post("/products/", json=payload)
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ── Price validation ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad_price", [0, -1, -100.5, 0.0])
def test_invalid_price_rejected(client, bad_price):
    vendor_id = _create_vendor(client)
    payload = {**_valid_product(vendor_id), "price": bad_price}
    resp = client.post("/products/", json=payload)
    assert resp.status_code == 422, f"Expected 422 for price={bad_price}"


# ── Name validation ───────────────────────────────────────────────────────────

def test_blank_product_name_rejected(client):
    vendor_id = _create_vendor(client)
    payload = {**_valid_product(vendor_id), "name": "   "}
    resp = client.post("/products/", json=payload)
    assert resp.status_code == 422


def test_missing_product_name_rejected(client):
    vendor_id = _create_vendor(client)
    payload = {k: v for k, v in _valid_product(vendor_id).items() if k != "name"}
    resp = client.post("/products/", json=payload)
    assert resp.status_code == 422


# ── Retrieval ─────────────────────────────────────────────────────────────────

def test_get_product_by_id(client):
    vendor_id = _create_vendor(client)
    create_resp = client.post("/products/", json=_valid_product(vendor_id))
    product_id = create_resp.json()["id"]
    resp = client.get(f"/products/{product_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == product_id


def test_get_product_not_found(client):
    resp = client.get("/products/99999")
    assert resp.status_code == 404


def test_list_products(client):
    vendor_id = _create_vendor(client)
    client.post("/products/", json=_valid_product(vendor_id))
    resp = client.get("/products/")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_list_products_filtered_by_vendor(client):
    vendor_id = _create_vendor(client)
    client.post("/products/", json=_valid_product(vendor_id))
    resp = client.get(f"/products/?vendor_id={vendor_id}")
    assert resp.status_code == 200
    products = resp.json()
    assert all(p["vendor_id"] == vendor_id for p in products)


def test_list_products_empty(client):
    resp = client.get("/products/")
    assert resp.status_code == 200
    assert resp.json() == []

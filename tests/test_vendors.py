"""
tests/test_vendors.py — Tests for vendor registration and validation.

Covers:
  - Successful registration of a valid vendor
  - Duplicate email rejection (HTTP 409)
  - Blank name rejection (HTTP 422)
  - Invalid email format rejection (HTTP 422)
  - Invalid phone format rejection (HTTP 422)
  - Retrieving a vendor by ID
  - Listing vendors
  - 404 for nonexistent vendor ID
  - Optional address field
  - Phone edge cases
"""

import pytest


VALID_VENDOR = {
    "name": "TechZone India",
    "email": "techzone@example.com",
    "phone": "+91-9876543210",
    "address": "123 MG Road, Bengaluru",
}


# ── Registration success ──────────────────────────────────────────────────────

def test_create_vendor_success(client):
    resp = client.post("/vendors/", json=VALID_VENDOR)
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == VALID_VENDOR["email"]
    assert data["name"] == VALID_VENDOR["name"]
    assert "id" in data
    assert "created_at" in data


def test_create_vendor_without_address(client):
    payload = {**VALID_VENDOR, "address": None, "email": "noaddr@example.com"}
    resp = client.post("/vendors/", json=payload)
    assert resp.status_code == 201
    assert resp.json()["address"] is None


# ── Duplicate email ───────────────────────────────────────────────────────────

def test_duplicate_email_rejected(client):
    client.post("/vendors/", json=VALID_VENDOR)  # first registration
    resp = client.post("/vendors/", json=VALID_VENDOR)  # duplicate
    assert resp.status_code == 409
    assert "already registered" in resp.json()["detail"].lower()


def test_duplicate_email_case_is_unique(client):
    """Same characters, different case — treat as different emails per RFC."""
    client.post("/vendors/", json=VALID_VENDOR)
    payload2 = {**VALID_VENDOR, "email": "TECHZONE@EXAMPLE.COM"}
    resp = client.post("/vendors/", json=payload2)
    # EmailStr normalises to lowercase, so this SHOULD be a duplicate
    assert resp.status_code == 409


# ── Blank / missing fields ────────────────────────────────────────────────────

def test_blank_name_rejected(client):
    payload = {**VALID_VENDOR, "name": "   ", "email": "blank@test.com"}
    resp = client.post("/vendors/", json=payload)
    assert resp.status_code == 422


def test_missing_name_rejected(client):
    payload = {k: v for k, v in VALID_VENDOR.items() if k != "name"}
    resp = client.post("/vendors/", json=payload)
    assert resp.status_code == 422


def test_missing_email_rejected(client):
    payload = {k: v for k, v in VALID_VENDOR.items() if k != "email"}
    resp = client.post("/vendors/", json=payload)
    assert resp.status_code == 422


def test_missing_phone_rejected(client):
    payload = {k: v for k, v in VALID_VENDOR.items() if k != "phone"}
    resp = client.post("/vendors/", json=payload)
    assert resp.status_code == 422


# ── Email validation ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad_email", [
    "notanemail",
    "missing@",
    "@nodomain.com",
    "spaces in@email.com",
    "",
])
def test_invalid_email_rejected(client, bad_email):
    payload = {**VALID_VENDOR, "email": bad_email}
    resp = client.post("/vendors/", json=payload)
    assert resp.status_code == 422, f"Expected 422 for email={bad_email!r}"


# ── Phone validation ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("good_phone,idx", [
    ("+91-9876543210", 1),
    ("9876543210", 2),
    ("+1 (800) 555-1234", 3),
    ("040-27654321", 4),
])
def test_valid_phones_accepted(client, good_phone, idx):
    payload = {**VALID_VENDOR, "email": f"vendor{idx}@test.com", "phone": good_phone}
    resp = client.post("/vendors/", json=payload)
    assert resp.status_code == 201, f"Expected 201 for phone={good_phone!r}, got {resp.status_code}: {resp.json()}"


@pytest.mark.parametrize("bad_phone", [
    "abc",          # letters not allowed
    "123",          # too short
    "12345678901234567890123",  # too long
    "",             # blank
])
def test_invalid_phones_rejected(client, bad_phone):
    payload = {**VALID_VENDOR, "email": "phonetest@test.com", "phone": bad_phone}
    resp = client.post("/vendors/", json=payload)
    assert resp.status_code == 422, f"Expected 422 for phone={bad_phone!r}"


# ── Retrieval ─────────────────────────────────────────────────────────────────

def test_get_vendor_by_id(client):
    create_resp = client.post("/vendors/", json=VALID_VENDOR)
    vendor_id = create_resp.json()["id"]
    resp = client.get(f"/vendors/{vendor_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == vendor_id


def test_get_vendor_not_found(client):
    resp = client.get("/vendors/99999")
    assert resp.status_code == 404


def test_list_vendors(client):
    client.post("/vendors/", json=VALID_VENDOR)
    resp = client.get("/vendors/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


def test_list_vendors_empty(client):
    resp = client.get("/vendors/")
    assert resp.status_code == 200
    assert resp.json() == []

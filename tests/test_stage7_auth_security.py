"""
tests/test_stage7_auth_security.py — Automated Test Suite for Stage 7: Authentication, JWT Security, RBAC & Multi-Tenant Access Control.

Covers 37 Security Scenarios:
1-5:   Password Hashing, Verification, Salt Uniqueness, and Cryptographic Security
6-11:  JWT Access/Refresh Token Generation, Claims Verification, Expiration & Tampering
12-15: Public Customer Registration, Role Escalation Rejection & Profile Linking
16-19: Authentication, Credential Verification, User Enumeration Protection & Deactivated Accounts
20-24: Refresh Token Rotation, Replay/Reuse Family Revocation & Session Termination
25-27: Self-Service Password Management, Credential Updates & Session Invalidation
28-32: Role-Based Access Control (ADMIN, VENDOR, CUSTOMER, Unauthenticated)
33-37: Backend Multi-Tenant Vendor Isolation & Customer Data Ownership
"""

import uuid
from datetime import datetime, timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.user import User, RefreshToken, UserRole
from app.models.vendor import Vendor
from app.models.customer import Customer
from app.models.product import Product
from app.models.transaction import Transaction
from app.core.security import (
    hash_password,
    verify_password,
    hash_token,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.services.auth.auth_service import AuthService
from app.schemas.auth_schema import (
    UserRegisterRequest,
    AdminCreateUserRequest,
    AdminUpdateUserStatusRequest,
    AdminUpdateUserRoleRequest,
)


# ── Helper Fixtures & Builders ───────────────────────────────────────────────

def _create_user(db: Session, email: str, role: str, password: str = "SecurePass123!", vendor_id=None, customer_id=None, is_active=True) -> User:
    """Helper to persist a user account directly."""
    user = User(
        email=email.lower(),
        hashed_password=hash_password(password),
        role=role,
        vendor_id=vendor_id,
        customer_id=customer_id,
        is_active=is_active,
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_header(user: User) -> dict:
    """Helper to generate Authorization header for a given user."""
    token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        vendor_id=user.vendor_id,
        customer_id=user.customer_id,
        token_version=user.token_version or 1,
    )
    return {"Authorization": f"Bearer {token}", "X-Enforce-Auth": "true"}


# ── Category 1: Password Hashing & Cryptography (5 Scenarios) ─────────────────

def test_01_password_hash_generation_and_verification():
    """Verify bcrypt hashes plaintext and verifies correctly."""
    pwd = "MySecretPassword123!"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert hashed.startswith("$2b$")
    assert verify_password(pwd, hashed) is True


def test_02_password_hash_salt_uniqueness():
    """Verify salt randomness ensures identical passwords produce distinct hashes."""
    pwd = "IdenticalPassword999!"
    h1 = hash_password(pwd)
    h2 = hash_password(pwd)
    assert h1 != h2
    assert verify_password(pwd, h1) is True
    assert verify_password(pwd, h2) is True


def test_03_password_verification_rejects_wrong_password():
    """Verify incorrect password fails constant-time check."""
    hashed = hash_password("CorrectPassword123!")
    assert verify_password("WrongPassword123!", hashed) is False
    assert verify_password("", hashed) is False


def test_04_empty_password_rejection():
    """Verify empty password raises ValueError."""
    with pytest.raises(ValueError, match="Password cannot be empty"):
        hash_password("")


def test_05_token_sha256_hashing():
    """Verify SHA-256 token hashing produces deterministic 64-char hex digest."""
    t1 = "test-jwt-token-string-12345"
    d1 = hash_token(t1)
    d2 = hash_token(t1)
    assert len(d1) == 64
    assert d1 == d2
    assert d1 != hash_token("different-token")


# ── Category 2: JWT Access & Refresh Tokens (6 Scenarios) ─────────────────────

def test_06_jwt_access_token_creation_and_claims():
    """Verify access token contains expected claims (sub, email, role, type, jti, exp)."""
    token = create_access_token(user_id=42, email="user@shopsense.com", role="ADMIN")
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "42"
    assert payload["email"] == "user@shopsense.com"
    assert payload["role"] == "ADMIN"
    assert payload["type"] == "access"
    assert "jti" in payload
    assert payload["exp"] > payload["iat"]


def test_07_jwt_token_decoding_valid():
    """Verify decode_token successfully decodes a valid token."""
    token = create_access_token(user_id=10, email="test@example.com", role="VENDOR", vendor_id=3)
    payload = decode_token(token)
    assert payload["vendor_id"] == 3
    assert payload["sub"] == "10"


def test_08_jwt_expired_token_rejection():
    """Verify expired token is rejected with HTTP 401 Unauthorized."""
    expired_delta = timedelta(seconds=-10)
    token = create_access_token(user_id=1, email="exp@test.com", role="CUSTOMER", expires_delta=expired_delta)
    with pytest.raises(HTTPException) as exc:
        decode_token(token, expected_type="access")
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


def test_09_jwt_tampered_signature_rejection():
    """Verify token with forged/tampered signature is rejected with HTTP 401."""
    token = create_access_token(user_id=1, email="legit@test.com", role="CUSTOMER")
    parts = token.split(".")
    # Tamper with signature
    tampered = f"{parts[0]}.{parts[1]}.tampered_invalid_signature"
    with pytest.raises(HTTPException) as exc:
        decode_token(tampered)
    assert exc.value.status_code == 401
    assert "invalid" in exc.value.detail.lower()


def test_10_jwt_wrong_type_rejection():
    """Verify presenting a refresh token when an access token is expected fails."""
    t_str, _, _, _, _ = create_refresh_token(user_id=1, email="test@test.com", role="CUSTOMER")
    with pytest.raises(HTTPException) as exc:
        decode_token(t_str, expected_type="access")
    assert exc.value.status_code == 401
    assert "invalid token type" in exc.value.detail.lower()


def test_11_jwt_refresh_token_creation():
    """Verify refresh token creation returns token string, hash, family UUID, and expiry."""
    t_str, t_hash, family, jti, expire = create_refresh_token(user_id=5, email="ref@test.com", role="VENDOR")
    assert isinstance(t_str, str)
    assert len(t_hash) == 64
    assert len(family) == 36  # UUID
    assert len(jti) == 36
    assert expire > datetime.utcnow()


# ── Category 3: User Registration & Validation (4 Scenarios) ──────────────────

def test_12_public_registration_creates_customer(client, db_session):
    """Verify public registration creates a verified CUSTOMER user account."""
    resp = client.post("/auth/register", json={
        "email": "newcustomer@example.com",
        "password": "Password1234!",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "newcustomer@example.com"
    assert data["role"] == "CUSTOMER"
    assert data["is_active"] is True

    # Check password is never returned and hashed in DB
    user = db_session.query(User).filter(User.email == "newcustomer@example.com").first()
    assert user is not None
    assert user.hashed_password != "Password1234!"
    assert verify_password("Password1234!", user.hashed_password) is True


def test_13_public_registration_role_escalation_prevented(client, db_session):
    """Verify role escalation payloads in public registration are strictly ignored/prevented."""
    resp = client.post("/auth/register", json={
        "email": "attacker@example.com",
        "password": "AttackerPass123!",
        "role": "ADMIN",  # Attempt escalation
    })
    assert resp.status_code == 201
    data = resp.json()
    # Must strictly be assigned CUSTOMER
    assert data["role"] == "CUSTOMER"


def test_14_registration_duplicate_email_rejected(client, db_session):
    """Verify registration with duplicate email returns 400 Bad Request."""
    _create_user(db_session, email="dupe@example.com", role=UserRole.CUSTOMER)
    resp = client.post("/auth/register", json={
        "email": "dupe@example.com",
        "password": "Password123!",
    })
    assert resp.status_code == 400
    assert "already registered" in resp.json()["detail"].lower()


def test_15_registration_links_existing_customer(client, db_session):
    """Verify registration can link an existing unlinked customer profile."""
    cust = Customer(name="Alice Shopper", email="alice@test.com", city="Seattle", region="West")
    db_session.add(cust)
    db_session.commit()
    db_session.refresh(cust)

    resp = client.post("/auth/register", json={
        "email": "alice@test.com",
        "password": "AlicePassword123!",
        "customer_id": cust.customer_id,
    })
    assert resp.status_code == 201
    assert resp.json()["customer_id"] == cust.customer_id


# ── Category 4: Authentication & Credential Verification (4 Scenarios) ────────

def test_16_login_success_issues_jwt_pair(client, db_session):
    """Verify valid login returns access_token, refresh_token, and user metadata."""
    _create_user(db_session, email="login_user@example.com", role=UserRole.CUSTOMER, password="SecretPass123!")
    resp = client.post("/auth/login", json={
        "email": "login_user@example.com",
        "password": "SecretPass123!",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["email"] == "login_user@example.com"
    assert data["role"] == "CUSTOMER"


def test_17_login_invalid_password_returns_generic_401(client, db_session):
    """Verify bad password returns generic 401 error against user enumeration."""
    _create_user(db_session, email="valid_user@example.com", role=UserRole.CUSTOMER, password="CorrectPassword!")
    resp = client.post("/auth/login", json={
        "email": "valid_user@example.com",
        "password": "WrongPassword999!",
    })
    assert resp.status_code == 401
    assert "incorrect email or password" in resp.json()["detail"].lower()


def test_18_login_unknown_email_returns_generic_401(client):
    """Verify non-existent email returns same generic 401 to prevent enumeration."""
    resp = client.post("/auth/login", json={
        "email": "nonexistent_email_12345@example.com",
        "password": "AnyPassword123!",
    })
    assert resp.status_code == 401
    assert "incorrect email or password" in resp.json()["detail"].lower()


def test_19_login_deactivated_account_rejected(client, db_session):
    """Verify deactivated account is rejected with HTTP 403 Forbidden."""
    _create_user(db_session, email="banned@example.com", role=UserRole.CUSTOMER, is_active=False)
    resp = client.post("/auth/login", json={
        "email": "banned@example.com",
        "password": "SecurePass123!",
    })
    assert resp.status_code == 403
    assert "inactive or disabled" in resp.json()["detail"].lower()


# ── Category 5: Token Rotation & Family Reuse Detection (5 Scenarios) ─────────

def test_20_refresh_token_rotation_success(client, db_session):
    """Verify refresh token rotation returns new access token and rotated refresh token."""
    user = _create_user(db_session, email="rotator@example.com", role=UserRole.CUSTOMER)
    login_resp = client.post("/auth/login", json={"email": "rotator@example.com", "password": "SecurePass123!"})
    r1 = login_resp.json()["refresh_token"]

    rotate_resp = client.post("/auth/refresh", json={"refresh_token": r1})
    assert rotate_resp.status_code == 200
    data = rotate_resp.json()
    r2 = data["refresh_token"]
    assert r2 != r1
    assert "access_token" in data


def test_21_refresh_token_reuse_detection_revokes_entire_family(client, db_session):
    """
    CRITICAL SECURITY INVARIANT:
    If a previously rotated (revoked) refresh token is reused,
    all active refresh tokens in that family must be immediately invalidated.
    """
    user = _create_user(db_session, email="victim@example.com", role=UserRole.CUSTOMER)
    login_resp = client.post("/auth/login", json={"email": "victim@example.com", "password": "SecurePass123!"})
    r1 = login_resp.json()["refresh_token"]

    # Legitimate rotation 1: r1 -> r2
    rot1 = client.post("/auth/refresh", json={"refresh_token": r1})
    assert rot1.status_code == 200
    r2 = rot1.json()["refresh_token"]

    # ATTACK: Attacker replays compromised r1
    replay_resp = client.post("/auth/refresh", json={"refresh_token": r1})
    assert replay_resp.status_code == 401
    assert "reuse detected" in replay_resp.json()["detail"].lower()

    # Now legitimate r2 must also be revoked because the entire family was invalidated!
    followup_resp = client.post("/auth/refresh", json={"refresh_token": r2})
    assert followup_resp.status_code == 401


def test_22_refresh_token_expired_rejected(client, db_session):
    """Verify expired refresh token is rejected with 401."""
    user = _create_user(db_session, email="exp_ref@example.com", role=UserRole.CUSTOMER)
    t_str, t_hash, fam, jti, _ = create_refresh_token(
        user.id, user.email, user.role, expires_delta=timedelta(seconds=-10)
    )
    rec = RefreshToken(
        user_id=user.id, token_hash=t_hash, token_family=fam, jti=jti,
        is_revoked=False, expires_at=datetime.utcnow() - timedelta(seconds=10),
    )
    db_session.add(rec)
    db_session.commit()

    resp = client.post("/auth/refresh", json={"refresh_token": t_str})
    assert resp.status_code == 401


def test_23_user_logout_revokes_single_token(client, db_session):
    """Verify /auth/logout revokes the submitted refresh token."""
    user = _create_user(db_session, email="logout_user@example.com", role=UserRole.CUSTOMER)
    login_resp = client.post("/auth/login", json={"email": "logout_user@example.com", "password": "SecurePass123!"})
    tokens = login_resp.json()

    headers = {"Authorization": f"Bearer {tokens['access_token']}", "X-Enforce-Auth": "true"}
    logout_resp = client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]}, headers=headers)
    assert logout_resp.status_code == 200

    # Attempting to refresh with the revoked token must fail
    ref_resp = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert ref_resp.status_code == 401


def test_24_user_logout_all_revokes_all_sessions(client, db_session):
    """Verify /auth/logout-all invalidates all active sessions for the user."""
    user = _create_user(db_session, email="multi_session@example.com", role=UserRole.CUSTOMER)
    # Login on device 1
    t1 = client.post("/auth/login", json={"email": "multi_session@example.com", "password": "SecurePass123!"}).json()
    # Login on device 2
    t2 = client.post("/auth/login", json={"email": "multi_session@example.com", "password": "SecurePass123!"}).json()

    headers = {"Authorization": f"Bearer {t1['access_token']}", "X-Enforce-Auth": "true"}
    logout_all = client.post("/auth/logout-all", headers=headers)
    assert logout_all.status_code == 200

    # Both refresh tokens must now be rejected
    assert client.post("/auth/refresh", json={"refresh_token": t1["refresh_token"]}).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": t2["refresh_token"]}).status_code == 401


# ── Category 6: Self-Service & Admin Password Management (3 Scenarios) ────────

def test_25_change_password_success_and_invalidates_sessions(client, db_session):
    """Verify changing password updates hash and revokes existing refresh tokens."""
    user = _create_user(db_session, email="pwd_change@example.com", role=UserRole.CUSTOMER, password="OldPassword123!")
    login_resp = client.post("/auth/login", json={"email": "pwd_change@example.com", "password": "OldPassword123!"})
    tokens = login_resp.json()

    headers = {"Authorization": f"Bearer {tokens['access_token']}", "X-Enforce-Auth": "true"}
    resp = client.post("/auth/change-password", json={
        "current_password": "OldPassword123!",
        "new_password": "BrandNewPassword123!",
    }, headers=headers)
    assert resp.status_code == 200

    # Verify old password no longer works
    assert client.post("/auth/login", json={"email": "pwd_change@example.com", "password": "OldPassword123!"}).status_code == 401
    # Verify new password works
    assert client.post("/auth/login", json={"email": "pwd_change@example.com", "password": "BrandNewPassword123!"}).status_code == 200
    # Verify old refresh token was invalidated
    assert client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_26_change_password_incorrect_current_rejected(client, db_session):
    """Verify incorrect current password returns 400 Bad Request."""
    user = _create_user(db_session, email="wrong_pwd@example.com", role=UserRole.CUSTOMER, password="RealPassword123!")
    headers = _auth_header(user)
    resp = client.post("/auth/change-password", json={
        "current_password": "WrongPassword999!",
        "new_password": "NewPassword123!",
    }, headers=headers)
    assert resp.status_code == 400
    assert "incorrect" in resp.json()["detail"].lower()


def test_27_change_password_identical_rejected(client, db_session):
    """Verify submitting identical new password returns 400 Bad Request."""
    user = _create_user(db_session, email="same_pwd@example.com", role=UserRole.CUSTOMER, password="SamePassword123!")
    headers = _auth_header(user)
    resp = client.post("/auth/change-password", json={
        "current_password": "SamePassword123!",
        "new_password": "SamePassword123!",
    }, headers=headers)
    assert resp.status_code == 400
    assert "must be different" in resp.json()["detail"].lower()


# ── Category 7: Role-Based Access Control (RBAC) (5 Scenarios) ─────────────────

def test_28_admin_endpoint_allows_admin(client, db_session):
    """Verify ADMIN user can access administrative endpoints."""
    admin = _create_user(db_session, email="admin_test@example.com", role=UserRole.ADMIN)
    headers = _auth_header(admin)
    resp = client.get("/auth/admin/users", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_29_admin_endpoint_rejects_vendor(client, db_session):
    """Verify VENDOR user is rejected with 403 Forbidden on administrative endpoints."""
    vendor = _create_user(db_session, email="vendor_test@example.com", role=UserRole.VENDOR, vendor_id=1)
    headers = _auth_header(vendor)
    resp = client.get("/auth/admin/users", headers=headers)
    assert resp.status_code == 403
    assert "administrative privileges required" in resp.json()["detail"].lower()


def test_30_admin_endpoint_rejects_customer(client, db_session):
    """Verify CUSTOMER user is rejected with 403 Forbidden on administrative endpoints."""
    customer = _create_user(db_session, email="cust_test@example.com", role=UserRole.CUSTOMER)
    headers = _auth_header(customer)
    resp = client.get("/auth/admin/users", headers=headers)
    assert resp.status_code == 403


def test_31_admin_endpoint_rejects_unauthenticated(client):
    """Verify unauthenticated requests to protected endpoints return 401 Unauthorized."""
    # /auth/me strictly requires authentication
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_32_admin_can_update_user_status_and_role(client, db_session):
    """Verify ADMIN can deactivate a user and change user roles."""
    admin = _create_user(db_session, email="superadmin@example.com", role=UserRole.ADMIN)
    target = _create_user(db_session, email="target_user@example.com", role=UserRole.CUSTOMER)
    headers = _auth_header(admin)

    # Deactivate user
    patch_resp = client.patch(f"/auth/admin/users/{target.id}/status", json={"is_active": False}, headers=headers)
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False

    # Promote to ADMIN
    role_resp = client.patch(f"/auth/admin/users/{target.id}/role", json={"role": "ADMIN"}, headers=headers)
    assert role_resp.status_code == 200
    assert role_resp.json()["role"] == "ADMIN"


# ── Category 8: Multi-Tenant Vendor Isolation & Ownership (5 Scenarios) ───────

def test_33_vendor_cannot_create_product_for_another_vendor(client, db_session):
    """
    CRITICAL MULTI-TENANT INVARIANT:
    Vendor user linked to vendor_id=1 cannot create a product for vendor_id=2.
    Must be rejected with HTTP 403 Forbidden.
    """
    v1 = Vendor(name="Vendor One", email="v1@test.com", phone="1234567890", status="ACTIVE", commission_tier="TIER_STANDARD")
    v2 = Vendor(name="Vendor Two", email="v2@test.com", phone="0987654321", status="ACTIVE", commission_tier="TIER_STANDARD")
    db_session.add_all([v1, v2])
    db_session.commit()
    db_session.refresh(v1)
    db_session.refresh(v2)

    vendor_user = _create_user(db_session, email="vendor1_user@test.com", role=UserRole.VENDOR, vendor_id=v1.id)
    headers = _auth_header(vendor_user)

    # Attempt to post product under v2.id
    resp = client.post("/products/", json={
        "name": "Cross Vendor Product",
        "price": 100.0,
        "vendor_id": v2.id,
        "category": "Electronics",
    }, headers=headers)

    assert resp.status_code == 403
    assert "you do not have permission" in resp.json()["detail"].lower()


def test_34_vendor_can_create_product_for_own_vendor(client, db_session):
    """Verify Vendor user can successfully create a product for their own vendor_id."""
    v1 = Vendor(name="Vendor Clean", email="vclean@test.com", phone="1234567890", status="ACTIVE", commission_tier="TIER_STANDARD")
    db_session.add(v1)
    db_session.commit()
    db_session.refresh(v1)

    vendor_user = _create_user(db_session, email="vclean_user@test.com", role=UserRole.VENDOR, vendor_id=v1.id)
    headers = _auth_header(vendor_user)

    resp = client.post("/products/", json={
        "name": "Legitimate Vendor Product",
        "price": 45.0,
        "vendor_id": v1.id,
        "category": "Kitchen",
    }, headers=headers)

    assert resp.status_code == 201
    assert resp.json()["name"] == "Legitimate Vendor Product"
    assert resp.json()["vendor_id"] == v1.id


def test_35_vendor_cannot_update_product_of_another_vendor(client, db_session):
    """Verify Vendor user cannot modify a product belonging to another vendor."""
    v1 = Vendor(name="V1", email="v1_u@test.com", phone="1234567890", status="ACTIVE", commission_tier="TIER_STANDARD")
    v2 = Vendor(name="V2", email="v2_u@test.com", phone="0987654321", status="ACTIVE", commission_tier="TIER_STANDARD")
    db_session.add_all([v1, v2])
    db_session.commit()

    p2 = Product(name="V2 Item", price=20.0, category="Books", vendor_id=v2.id)
    db_session.add(p2)
    db_session.commit()
    db_session.refresh(p2)

    vendor_user = _create_user(db_session, email="v1_agent@test.com", role=UserRole.VENDOR, vendor_id=v1.id)
    headers = _auth_header(vendor_user)

    resp = client.put(f"/products/{p2.id}", json={"name": "Hacked Title"}, headers=headers)
    assert resp.status_code == 403
    assert "you do not have permission" in resp.json()["detail"].lower()


def test_36_vendor_cannot_view_payouts_of_another_vendor(client, db_session):
    """Verify Vendor user cannot query settlement payouts for another vendor."""
    v1 = Vendor(name="V1 Pay", email="v1_p@test.com", phone="1234567890", status="ACTIVE", commission_tier="TIER_STANDARD")
    v2 = Vendor(name="V2 Pay", email="v2_p@test.com", phone="0987654321", status="ACTIVE", commission_tier="TIER_STANDARD")
    db_session.add_all([v1, v2])
    db_session.commit()

    vendor_user = _create_user(db_session, email="v1_fin@test.com", role=UserRole.VENDOR, vendor_id=v1.id)
    headers = _auth_header(vendor_user)

    # Vendor 1 requests Vendor 2 payouts
    resp = client.get(f"/analytics/vendors/payouts?vendor_id={v2.id}", headers=headers)
    assert resp.status_code == 403
    assert "cannot view settlement data for another vendor" in resp.json()["detail"].lower()


def test_37_customer_cannot_access_another_customer_recommendations(client, db_session):
    """
    CRITICAL CUSTOMER PRIVACY INVARIANT:
    Customer 1 cannot request personalized recommendations for Customer 2.
    Must be rejected with HTTP 403 Forbidden.
    """
    c1 = Customer(name="Customer 1", email="c1@test.com", city="Austin", region="South")
    c2 = Customer(name="Customer 2", email="c2@test.com", city="Denver", region="West")
    db_session.add_all([c1, c2])
    db_session.commit()
    db_session.refresh(c1)
    db_session.refresh(c2)

    cust1_user = _create_user(db_session, email="c1_u@test.com", role=UserRole.CUSTOMER, customer_id=c1.customer_id)
    headers = _auth_header(cust1_user)

    # Customer 1 attempts to query recommendations for Customer 2
    resp = client.get(f"/recommendations/customer/{c2.customer_id}", headers=headers)
    assert resp.status_code == 403
    assert "you cannot view or modify data belonging to another customer" in resp.json()["detail"].lower()


# ── Category 8: Stage 7.1 Security Hardening & Session Revocation (Tests 38–46) ─

def test_38_access_token_invalidated_after_single_logout(client, db_session):
    """
    Verify that logging out revokes both the refresh token and blacklists the
    current access token JTI, immediately rejecting further use with HTTP 401.
    """
    user = _create_user(db_session, email="logout_test@test.com", role=UserRole.CUSTOMER)
    tokens = AuthService.issue_token_pair(db_session, user)
    access_token = tokens.access_token
    refresh_token = tokens.refresh_token

    auth_headers = {"Authorization": f"Bearer {access_token}", "X-Enforce-Auth": "true"}

    # Verified access works initially
    me_resp = client.get("/auth/me", headers=auth_headers)
    assert me_resp.status_code == 200

    # User logs out with access token header and refresh token body
    logout_resp = client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
        headers=auth_headers,
    )
    assert logout_resp.status_code == 200

    # Same access token is now blacklisted and must be rejected with 401
    me_after = client.get("/auth/me", headers=auth_headers)
    assert me_after.status_code == 401
    assert "revoked" in me_after.json()["detail"].lower()


def test_39_access_token_invalidated_after_logout_all(client, db_session):
    """
    Verify that calling logout-all bumps token_version and invalidates
    active access tokens across all devices with HTTP 401.
    """
    user = _create_user(db_session, email="logout_all_test@test.com", role=UserRole.CUSTOMER)
    tokens = AuthService.issue_token_pair(db_session, user)
    access_token = tokens.access_token

    auth_headers = {"Authorization": f"Bearer {access_token}", "X-Enforce-Auth": "true"}
    assert client.get("/auth/me", headers=auth_headers).status_code == 200

    # Call logout-all
    resp = client.post("/auth/logout-all", headers=auth_headers)
    assert resp.status_code == 200

    # Old access token with outdated token_version must be rejected
    resp_after = client.get("/auth/me", headers=auth_headers)
    assert resp_after.status_code == 401
    assert "session has been terminated" in resp_after.json()["detail"].lower()


def test_40_access_token_invalidated_after_password_change(client, db_session):
    """
    Verify password change invalidates all pre-existing access tokens via token_version.
    """
    user = _create_user(db_session, email="pwd_change_inv@test.com", role=UserRole.CUSTOMER, password="OldPassword123!")
    tokens = AuthService.issue_token_pair(db_session, user)
    old_access_token = tokens.access_token

    old_headers = {"Authorization": f"Bearer {old_access_token}", "X-Enforce-Auth": "true"}

    # Change password
    resp = client.post(
        "/auth/change-password",
        json={"current_password": "OldPassword123!", "new_password": "BrandNewPassword456!"},
        headers=old_headers,
    )
    assert resp.status_code == 200

    # Pre-existing access token is now invalid
    resp_old = client.get("/auth/me", headers=old_headers)
    assert resp_old.status_code == 401
    assert "session has been terminated" in resp_old.json()["detail"].lower()


def test_41_access_token_invalidated_after_admin_role_change(client, db_session):
    """
    Verify that when an admin modifies a user's role or tenant linkage,
    the user's existing access token is immediately rejected due to token_version / role mismatch.
    """
    admin = _create_user(db_session, email="admin_role_changer@test.com", role=UserRole.ADMIN)
    target_user = _create_user(db_session, email="target_emp@test.com", role=UserRole.CUSTOMER)

    target_tokens = AuthService.issue_token_pair(db_session, target_user)
    target_access_token = target_tokens.access_token
    target_headers = {"Authorization": f"Bearer {target_access_token}", "X-Enforce-Auth": "true"}

    assert client.get("/auth/me", headers=target_headers).status_code == 200

    v = Vendor(name="Target Vendor", email="tv@test.com", phone="1234567890", status="ACTIVE", commission_tier="TIER_STANDARD")
    db_session.add(v)
    db_session.commit()
    db_session.refresh(v)

    # Admin changes user role from CUSTOMER to VENDOR
    admin_headers = _auth_header(admin)
    patch_resp = client.patch(
        f"/auth/admin/users/{target_user.id}/role",
        json={"role": "VENDOR", "vendor_id": v.id},
        headers=admin_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["role"] == "VENDOR"

    # Target user's pre-change token is now rejected
    resp_after = client.get("/auth/me", headers=target_headers)
    assert resp_after.status_code == 401


def test_42_customer_registration_with_mismatched_customer_id_rejected(client, db_session):
    """
    Verify an attacker cannot claim a pre-existing customer profile
    merely by submitting an arbitrary customer_id with a different email.
    """
    c = Customer(name="Real Customer", email="real_customer@test.com", city="Dallas", region="South")
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)

    # Attacker tries to register under attacker@evil.com with c.customer_id
    payload = {
        "email": "attacker@evil.com",
        "password": "AttackerPass123!",
        "customer_id": c.customer_id,
    }
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 403
    assert "ownership verification failed" in resp.json()["detail"].lower()


def test_43_customer_cannot_access_another_customer_churn_and_clv(client, db_session):
    """
    Verify customer cannot query churn risk or CLV projections of another customer.
    """
    c1 = Customer(name="Cust Alpha", email="calpha@test.com", city="Boston", region="East")
    c2 = Customer(name="Cust Beta", email="cbeta@test.com", city="Chicago", region="Central")
    db_session.add_all([c1, c2])
    db_session.commit()
    db_session.refresh(c1)
    db_session.refresh(c2)

    user1 = _create_user(db_session, email="calpha_user@test.com", role=UserRole.CUSTOMER, customer_id=c1.customer_id)
    headers = _auth_header(user1)

    # Cust 1 tries to access Cust 2 churn
    resp_churn = client.get(f"/analytics/customers/churn/{c2.customer_id}", headers=headers)
    assert resp_churn.status_code == 403
    assert "cannot view or modify data belonging to another customer" in resp_churn.json()["detail"].lower()

    # Cust 1 tries to access Cust 2 clv
    resp_clv = client.get(f"/analytics/customers/clv/{c2.customer_id}", headers=headers)
    assert resp_clv.status_code == 403
    assert "cannot view or modify data belonging to another customer" in resp_clv.json()["detail"].lower()


def test_44_vendor_transactions_strictly_filtered_by_vendor_id(client, db_session):
    """
    Verify GET /analytics/transactions returns only own transactions for VENDOR role.
    """
    v1 = Vendor(name="V1 Txn", email="v1_t@test.com", phone="1234567890", status="ACTIVE", commission_tier="TIER_STANDARD")
    v2 = Vendor(name="V2 Txn", email="v2_t@test.com", phone="0987654321", status="ACTIVE", commission_tier="TIER_STANDARD")
    db_session.add_all([v1, v2])
    db_session.commit()
    db_session.refresh(v1)
    db_session.refresh(v2)

    p1 = Product(name="P1", price=50.0, category="Test", vendor_id=v1.id)
    p2 = Product(name="P2", price=60.0, category="Test", vendor_id=v2.id)
    c = Customer(name="Cust Txn", email="c_t@test.com", city="City", region="Region")
    db_session.add_all([p1, p2, c])
    db_session.commit()
    db_session.refresh(p1)
    db_session.refresh(p2)
    db_session.refresh(c)

    t1 = Transaction(
        transaction_id=9001,
        product_id=p1.id,
        vendor_id=v1.id,
        customer_id=c.customer_id,
        quantity=2,
        unit_price=50.0,
        amount=100.0,
        transaction_date=datetime.utcnow(),
    )
    t2 = Transaction(
        transaction_id=9002,
        product_id=p2.id,
        vendor_id=v2.id,
        customer_id=c.customer_id,
        quantity=1,
        unit_price=60.0,
        amount=60.0,
        transaction_date=datetime.utcnow(),
    )
    db_session.add_all([t1, t2])
    db_session.commit()

    vendor1_user = _create_user(db_session, email="v1_user_txn@test.com", role=UserRole.VENDOR, vendor_id=v1.id)
    headers = _auth_header(vendor1_user)

    resp = client.get("/analytics/transactions", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    # Ensure every transaction returned belongs strictly to v1
    for item in data:
        assert item["vendor_id"] == v1.id


def test_45_customer_cannot_record_stock_movement(client, db_session):
    """
    Verify customer role cannot record inventory stock movements (403 Forbidden).
    """
    v = Vendor(name="V Stock", email="vstock@test.com", phone="1234567890", status="ACTIVE", commission_tier="TIER_STANDARD")
    db_session.add(v)
    db_session.commit()
    db_session.refresh(v)

    p = Product(name="Stock Item", price=30.0, category="Items", vendor_id=v.id)
    c = Customer(name="Customer Stock", email="cstock@test.com", city="City", region="Region")
    db_session.add_all([p, c])
    db_session.commit()
    db_session.refresh(p)
    db_session.refresh(c)

    cust_user = _create_user(db_session, email="cust_stock@test.com", role=UserRole.CUSTOMER, customer_id=c.customer_id)
    headers = _auth_header(cust_user)

    resp = client.post(
        "/inventory/movements",
        json={
            "product_id": p.id,
            "movement_type": "RESTOCK",
            "quantity": 100,
        },
        headers=headers,
    )
    assert resp.status_code == 403
    assert "vendor or administrative privileges required" in resp.json()["detail"].lower()


def test_46_non_admin_cannot_access_etl_endpoints(client, db_session):
    """
    Verify non-admin roles (VENDOR, CUSTOMER) cannot access ETL batch endpoints.
    """
    v = Vendor(name="V ETL", email="vetl@test.com", phone="1234567890", status="ACTIVE", commission_tier="TIER_STANDARD")
    db_session.add(v)
    db_session.commit()
    db_session.refresh(v)

    vendor_user = _create_user(db_session, email="vetl_user@test.com", role=UserRole.VENDOR, vendor_id=v.id)
    headers = _auth_header(vendor_user)

    resp = client.get("/etl/batches", headers=headers)
    assert resp.status_code == 403
    assert "administrative privileges required" in resp.json()["detail"].lower()


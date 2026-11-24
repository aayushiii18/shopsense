"""
app/core/security.py — Cryptographic security utilities for ShopSense.

Stage 7: Authentication, JWT Security, RBAC & Multi-Tenant Access Control.
Provides:
- Bcrypt password hashing and constant-time verification.
- SHA-256 token hashing for database storage of refresh tokens.
- Cryptographically signed JWT access tokens (short-lived).
- Cryptographically signed JWT refresh tokens with rotation and token family tracking.
- Token decoding and signature validation.
- Preserves interim loopback verification (verify_loopback_only) for backward compatibility.
"""

import hashlib
import ipaddress
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, Any

import bcrypt
import jwt
from fastapi import Request, HTTPException, status

from app.core.config import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    BCRYPT_ROUNDS,
)

logger = logging.getLogger(__name__)

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}

# In-memory revocation cache for active access tokens (checked on every authenticated request)
_REVOKED_ACCESS_JTIS: set = set()


def revoke_access_jti(jti: str) -> None:
    """Revoke an individual access token by its JTI."""
    if jti:
        _REVOKED_ACCESS_JTIS.add(str(jti))


def is_access_jti_revoked(jti: str) -> bool:
    """Check if an access token JTI has been revoked."""
    if not jti:
        return False
    return str(jti) in _REVOKED_ACCESS_JTIS


# ── Password Hashing & Verification ──────────────────────────────────────────

def hash_password(password: str) -> str:
    """
    Hash a plaintext password using bcrypt with configured work factor.
    """
    if not password:
        raise ValueError("Password cannot be empty.")
    # bcrypt max length is 72 bytes
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a stored bcrypt hash in constant time.
    """
    if not plain_password or not hashed_password:
        return False
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception as exc:
        logger.error("Password verification error: %s", exc)
        return False


def hash_token(token: str) -> str:
    """
    Compute SHA-256 hash of a token string for safe storage in the database.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── JWT Token Generation & Verification ─────────────────────────────────────

def create_access_token(
    user_id: int,
    email: str,
    role: str,
    vendor_id: Optional[int] = None,
    customer_id: Optional[int] = None,
    token_version: int = 1,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT access token.
    Claims: sub (user_id), email, role, vendor_id, customer_id, token_version, type="access", jti, iat, exp.
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    jti = str(uuid.uuid4())

    payload = {
        "sub": str(user_id),
        "email": email.lower(),
        "role": role.upper(),
        "vendor_id": vendor_id,
        "customer_id": customer_id,
        "token_version": token_version,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": jti,
    }

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(
    user_id: int,
    email: str,
    role: str,
    token_family: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> Tuple[str, str, str, str, datetime]:
    """
    Create a signed JWT refresh token and return:
    (token_str, token_hash, token_family, jti, expires_at)
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    jti = str(uuid.uuid4())
    family = token_family or str(uuid.uuid4())

    payload = {
        "sub": str(user_id),
        "email": email.lower(),
        "role": role.upper(),
        "family": family,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": jti,
    }

    token_str = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    token_digest = hash_token(token_str)
    # Return naive UTC datetime for DB storage compatibility
    expire_naive = expire.astimezone(timezone.utc).replace(tzinfo=None)
    return token_str, token_digest, family, jti, expire_naive


def decode_token(token: str, expected_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Decode and cryptographically verify a JWT token.
    Validates signature, expiration, and optionally token type ('access' or 'refresh').
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        logger.warning("Invalid token received: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or malformed token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if expected_type and payload.get("type") != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token type. Expected '{expected_type}' token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jti = payload.get("jti")
    if jti and is_access_jti_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked. Please re-authenticate.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


# ── Interim Loopback Gate Preservation ──────────────────────────────────────

def is_loopback_address(host: str) -> bool:
    """Check if host string is a recognized loopback or local testing interface."""
    if not host:
        return False
    host_clean = host.strip().lower()
    if host_clean in LOOPBACK_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host_clean)
        return ip.is_loopback
    except ValueError:
        return False


def verify_loopback_only(request: Request) -> bool:
    """
    FastAPI dependency enforcing local loopback access on sensitive endpoints.
    Preserved for backward-compatibility during Stage 7 transition.
    """
    client = request.client
    if not client or not client.host:
        logger.warning("Interim security gate: Rejecting request without verifiable client host.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Client locality cannot be verified (fail-closed policy).",
        )

    client_host = client.host
    if not is_loopback_address(client_host):
        logger.warning(
            "Interim security gate: Denied remote access to sensitive endpoint from %s",
            client_host,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Access restricted to local administrative loopback interface (127.0.0.1 / ::1). "
                f"Remote host '{client_host}' is unauthorized."
            ),
        )

    operator_id = request.headers.get("X-Audit-Operator-ID", "local-system")
    audit_reason = request.headers.get("X-Audit-Reason", "administrative-action")
    logger.info(
        "Interim security gate: Authorized loopback request from %s (Operator: %s, Reason: %s)",
        client_host,
        operator_id,
        audit_reason,
    )
    return True

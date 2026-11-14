"""
app/core/security.py — Interim security gate for Stages 4 & 5.

Enforces loopback-only restrictions on sensitive administrative and financial endpoints:
- PUT /vendors/{id}/status
- POST /refunds/
- GET /analytics/vendors/payouts

Safeguards:
- Supports IPv4 (127.0.0.1) and IPv6 (::1, ::ffff:127.0.0.1) loopback addresses.
- Recognizes pytest TestClient ("testclient").
- Ignores untrusted external X-Forwarded-For headers to prevent spoofing.
- Fails closed with HTTP 403 Forbidden if client locality cannot be verified.
- Documents that audit headers (X-Audit-Operator, X-Audit-Reason) provide traceability only,
  never authentication. Full RBAC arrives in Stage 7.
"""

import ipaddress
import logging
from fastapi import Request, HTTPException, status

logger = logging.getLogger(__name__)

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


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
    Fails closed with HTTP 403 Forbidden on remote or unverified clients.
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

    # Log audit metadata for traceability
    operator_id = request.headers.get("X-Audit-Operator-ID", "local-system")
    audit_reason = request.headers.get("X-Audit-Reason", "administrative-action")
    logger.info(
        "Interim security gate: Authorized loopback request from %s (Operator: %s, Reason: %s)",
        client_host,
        operator_id,
        audit_reason,
    )
    return True

"""
app/routes/auth_routes.py — Authentication, Token, and User Management API Endpoints.

Stage 7: Authentication, JWT Security, RBAC & Multi-Tenant Access Control.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.auth_schema import (
    UserRegisterRequest,
    VendorRegisterRequest,
    VendorRegisterResponse,
    UserLoginRequest,
    RefreshTokenRequest,
    ChangePasswordRequest,
    AdminCreateUserRequest,
    AdminUpdateUserStatusRequest,
    AdminUpdateUserRoleRequest,
    TokenResponse,
    UserResponse,
    MessageResponse,
)
from app.services.auth.auth_service import AuthService
from app.core.dependencies import (
    get_current_user,
    require_authenticated_user,
    require_admin,
)

router = APIRouter(prefix="/auth", tags=["Authentication & Access Control"])


# ── Public Endpoints ─────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Public customer registration",
)
def register_customer(payload: UserRegisterRequest, db: Session = Depends(get_db)):
    """
    Register a new customer account.
    Restricted to CUSTOMER role. Role escalation attempts are strictly prevented.
    """
    user = AuthService.register_customer(db, payload)
    return user


@router.post(
    "/register-vendor",
    response_model=VendorRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Public vendor application and account registration",
)
def register_vendor(payload: VendorRegisterRequest, db: Session = Depends(get_db)):
    """
    Register a new vendor store and linked VENDOR user atomically.
    Enforces PENDING_APPROVAL status pending administrator verification.
    """
    return AuthService.register_vendor(db, payload)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="User login with JWT issuance",
)
def login(payload: UserLoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate email and password and issue an access token and refresh token pair.
    Uses generic error messages to prevent account enumeration.
    """
    user = AuthService.authenticate_user(db, payload.email, payload.password)
    return AuthService.issue_token_pair(db, user)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token and issue new access token",
)
def refresh_token(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    """
    Rotate an existing refresh token with automatic reuse detection.
    If a revoked token is re-submitted, all sessions in its token family are immediately revoked.
    """
    return AuthService.rotate_refresh_token(db, payload.refresh_token)


# ── Authenticated User Endpoints ─────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
def get_current_user_profile(current_user: User = Depends(require_authenticated_user)):
    """Retrieve profile and role information for the currently authenticated user."""
    return current_user


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Revoke single refresh token session",
)
def logout(
    payload: RefreshTokenRequest,
    current_user: User = Depends(require_authenticated_user),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    """Revoke a specific refresh token session and blacklist the calling access token."""
    access_jti = None
    if authorization and authorization.startswith("Bearer "):
        try:
            from app.core.security import decode_token
            decoded = decode_token(authorization[7:].strip())
            access_jti = decoded.get("jti")
        except Exception:
            pass

    AuthService.revoke_refresh_token(db, payload.refresh_token, access_token_jti=access_jti)
    return MessageResponse(message="Successfully logged out of current session.")


@router.post(
    "/logout-all",
    response_model=MessageResponse,
    summary="Revoke all active sessions across all devices",
)
def logout_all_sessions(
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    """Revoke all active sessions for the current user."""
    count = AuthService.revoke_all_sessions(db, current_user.id)
    return MessageResponse(
        message=f"Successfully terminated {count} active session(s) across all devices."
    )


@router.post(
    "/change-password",
    response_model=MessageResponse,
    summary="Change user password",
)
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    """
    Change user password and terminate all active sessions to enforce re-login.
    """
    AuthService.change_password(
        db,
        current_user,
        payload.current_password,
        payload.new_password,
    )
    return MessageResponse(
        message="Password updated successfully. All active sessions have been invalidated."
    )


# ── Administrative Endpoints (ADMIN Role Required) ───────────────────────────

@router.post(
    "/admin/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Admin API", "Authentication & Access Control"],
    summary="Admin create user account (ADMIN, VENDOR, CUSTOMER)",
)
def admin_create_user(
    payload: AdminCreateUserRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Create a new user with specific role and optional vendor/customer linkage.
    Requires ADMIN privileges.
    """
    return AuthService.admin_create_user(db, payload)


@router.get(
    "/admin/users",
    response_model=List[UserResponse],
    tags=["Admin API", "Authentication & Access Control"],
    summary="Admin list all users",
)
def admin_list_users(
    role: Optional[str] = Query(None, description="Filter by role: ADMIN, VENDOR, CUSTOMER"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List system users with optional role filtering. Requires ADMIN privileges."""
    return AuthService.admin_list_users(db, role=role, skip=skip, limit=limit)


@router.get(
    "/admin/users/{user_id}",
    response_model=UserResponse,
    tags=["Admin API", "Authentication & Access Control"],
    summary="Admin get user details by ID",
)
def admin_get_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Fetch user by ID. Requires ADMIN privileges."""
    return AuthService.admin_get_user(db, user_id)


@router.patch(
    "/admin/users/{user_id}/status",
    response_model=UserResponse,
    tags=["Admin API", "Authentication & Access Control"],
    summary="Admin update user active/verified status",
)
def admin_update_user_status(
    user_id: int,
    payload: AdminUpdateUserStatusRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Activate or deactivate a user account.
    Deactivating a user revokes all their active sessions immediately.
    """
    return AuthService.admin_update_user_status(db, user_id, payload)


@router.patch(
    "/admin/users/{user_id}/role",
    response_model=UserResponse,
    tags=["Admin API", "Authentication & Access Control"],
    summary="Admin change user role and tenant linkage",
)
def admin_update_user_role(
    user_id: int,
    payload: AdminUpdateUserRoleRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Change user role and link to a vendor or customer entity.
    Invalidates existing sessions to enforce role change on next login.
    """
    return AuthService.admin_update_user_role(db, user_id, payload)

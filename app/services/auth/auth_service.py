"""
app/services/auth/auth_service.py — Business logic for authentication, tokens, and user management.

Stage 7: Authentication, JWT Security, RBAC & Multi-Tenant Access Control.
Provides:
- Public customer registration (restricts role escalation).
- Credential authentication with generic error messages against user enumeration.
- Access token issuance and refresh token rotation with token family reuse detection.
- Token revocation and multi-device session invalidation.
- Password updates with automatic session revocation.
- Administrative user lifecycle management.
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import ACCESS_TOKEN_EXPIRE_MINUTES
from app.core.security import (
    hash_password,
    verify_password,
    hash_token,
    create_access_token,
    create_refresh_token,
    decode_token,
    revoke_access_jti,
)
from app.models.user import User, RefreshToken, UserRole
from app.models.vendor import Vendor
from app.models.customer import Customer
from app.schemas.auth_schema import (
    UserRegisterRequest,
    AdminCreateUserRequest,
    AdminUpdateUserStatusRequest,
    AdminUpdateUserRoleRequest,
    TokenResponse,
)

logger = logging.getLogger(__name__)


class AuthService:
    """Authentication and session management service."""

    @staticmethod
    def register_customer(db: Session, req: UserRegisterRequest) -> User:
        """
        Public self-service customer registration.
        Guarantees:
        - Role is strictly forced to CUSTOMER (rejects escalation).
        - Unique email enforcement.
        - Links customer_id if provided or auto-links to existing customer by email.
        """
        email_clean = req.email.strip().lower()

        existing = db.query(User).filter(User.email == email_clean).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email address is already registered.",
            )

        linked_customer_id: Optional[int] = None
        if req.customer_id is not None:
            # Check customer exists
            cust = db.query(Customer).filter(Customer.customer_id == req.customer_id).first()
            if not cust:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Customer with ID {req.customer_id} does not exist.",
                )
            # CRITICAL SECURITY CHECK: Email must match target customer profile to prevent account theft
            if cust.email.strip().lower() != email_clean:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account ownership verification failed: Email address does not match target customer profile.",
                )
            # Check customer not already linked to another user
            linked_user = db.query(User).filter(User.customer_id == req.customer_id).first()
            if linked_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Customer ID {req.customer_id} is already linked to another user account.",
                )
            linked_customer_id = req.customer_id
        # Note: Unverified self-registration without verified matching ID does NOT auto-claim legacy accounts

        user = User(
            email=email_clean,
            hashed_password=hash_password(req.password),
            role=UserRole.CUSTOMER,  # strictly enforce CUSTOMER role
            customer_id=linked_customer_id,
            is_active=True,
            is_verified=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("New customer user registered: id=%s email=%s", user.id, user.email)
        return user

    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> User:
        """
        Authenticate user with email and password.
        Returns user on success, raises 401 on bad credentials (generic message to avoid enumeration).
        """
        email_clean = email.strip().lower()
        user = db.query(User).filter(User.email == email_clean).first()

        if not user or not verify_password(password, user.hashed_password):
            logger.warning("Failed login attempt for email: %s", email_clean)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            logger.warning("Login attempted for deactivated account: %s", email_clean)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive or disabled. Contact system administrator.",
            )

        user.last_login_at = datetime.utcnow()
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def issue_token_pair(db: Session, user: User) -> TokenResponse:
        """
        Issue a new JWT access token and refresh token for the user.
        """
        access_token = create_access_token(
            user_id=user.id,
            email=user.email,
            role=user.role,
            vendor_id=user.vendor_id,
            customer_id=user.customer_id,
            token_version=user.token_version or 1,
        )

        refresh_token_str, token_digest, family_id, jti, expire_dt = create_refresh_token(
            user_id=user.id,
            email=user.email,
            role=user.role,
        )

        db_refresh = RefreshToken(
            user_id=user.id,
            token_hash=token_digest,
            token_family=family_id,
            jti=jti,
            is_revoked=False,
            expires_at=expire_dt,
            created_at=datetime.utcnow(),
        )
        db.add(db_refresh)
        db.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token_str,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user_id=user.id,
            email=user.email,
            role=user.role,
            vendor_id=user.vendor_id,
            customer_id=user.customer_id,
        )

    @staticmethod
    def rotate_refresh_token(db: Session, refresh_token_str: str) -> TokenResponse:
        """
        Rotate an existing refresh token with reuse detection.
        If a revoked token in a family is presented, all tokens in that family are immediately revoked.
        """
        payload = decode_token(refresh_token_str, expected_type="refresh")
        digest = hash_token(refresh_token_str)

        token_record = db.query(RefreshToken).filter(RefreshToken.token_hash == digest).first()

        # Token reuse detection
        if token_record and token_record.is_revoked:
            logger.warning(
                "SECURITY ALERT: Refresh token reuse detected! Revoking entire token family %s",
                token_record.token_family,
            )
            # Revoke all tokens belonging to this family
            db.query(RefreshToken).filter(
                RefreshToken.token_family == token_record.token_family,
                RefreshToken.is_revoked == False,
            ).update(
                {"is_revoked": True, "revoked_at": datetime.utcnow()},
                synchronize_session=False,
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Security alert: Compromised refresh token reuse detected. All sessions in this family have been revoked.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not token_record or token_record.expires_at < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid, unknown, or expired refresh token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = db.query(User).filter(User.id == token_record.user_id).first()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive or disabled.",
            )

        # Mark present token as revoked (rotated)
        token_record.is_revoked = True
        token_record.revoked_at = datetime.utcnow()

        # Issue successor token maintaining token_family
        new_refresh_str, new_digest, family_id, new_jti, new_expire = create_refresh_token(
            user_id=user.id,
            email=user.email,
            role=user.role,
            token_family=token_record.token_family,
        )

        new_record = RefreshToken(
            user_id=user.id,
            token_hash=new_digest,
            token_family=family_id,
            jti=new_jti,
            is_revoked=False,
            expires_at=new_expire,
            created_at=datetime.utcnow(),
        )
        db.add(new_record)

        access_token = create_access_token(
            user_id=user.id,
            email=user.email,
            role=user.role,
            vendor_id=user.vendor_id,
            customer_id=user.customer_id,
            token_version=user.token_version or 1,
        )

        db.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_str,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user_id=user.id,
            email=user.email,
            role=user.role,
            vendor_id=user.vendor_id,
            customer_id=user.customer_id,
        )

    @staticmethod
    def revoke_refresh_token(db: Session, refresh_token_str: str, access_token_jti: Optional[str] = None) -> bool:
        """
        Revoke a single refresh token (user logout), and optionally blacklist the accompanying access token JTI.
        """
        if access_token_jti:
            revoke_access_jti(access_token_jti)

        try:
            decode_token(refresh_token_str, expected_type="refresh")
        except HTTPException:
            # Even if expired, try revoking by hash
            pass

        digest = hash_token(refresh_token_str)
        token_record = db.query(RefreshToken).filter(RefreshToken.token_hash == digest).first()
        if token_record and not token_record.is_revoked:
            token_record.is_revoked = True
            token_record.revoked_at = datetime.utcnow()
            db.commit()
            return True
        return False

    @staticmethod
    def revoke_all_sessions(db: Session, user_id: int) -> int:
        """
        Revoke all active refresh tokens for a user across all devices/sessions,
        and increment token_version to immediately invalidate all existing access tokens.
        """
        count = db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.is_revoked == False,
        ).update(
            {"is_revoked": True, "revoked_at": datetime.utcnow()},
            synchronize_session=False,
        )
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.token_version = (user.token_version or 1) + 1
            user.updated_at = datetime.utcnow()
        db.commit()
        logger.info("Revoked %s active session(s) and invalidated access tokens for user_id=%s", count, user_id)
        return count

    @staticmethod
    def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
        """
        Change user password and revoke all existing sessions to enforce re-login.
        """
        if not verify_password(current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect.",
            )

        if current_password == new_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be different from current password.",
            )

        user.hashed_password = hash_password(new_password)
        user.token_version = (user.token_version or 1) + 1
        user.updated_at = datetime.utcnow()

        # Revoke all active sessions and access tokens
        AuthService.revoke_all_sessions(db, user.id)
        db.commit()
        logger.info("Password successfully changed and sessions invalidated for user_id=%s", user.id)
        logger.info("Password successfully changed for user_id=%s", user.id)

    @staticmethod
    def admin_create_user(db: Session, req: AdminCreateUserRequest) -> User:
        """
        Create a user account with arbitrary role (ADMIN, VENDOR, CUSTOMER).
        Validates vendor/customer linkages.
        """
        email_clean = req.email.strip().lower()
        role_upper = req.role.upper()

        if role_upper not in UserRole.ALL_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role '{req.role}'. Must be one of: {list(UserRole.ALL_ROLES)}",
            )

        existing = db.query(User).filter(User.email == email_clean).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email address already exists.",
            )

        # Validate VENDOR link
        if role_upper == UserRole.VENDOR:
            if not req.vendor_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="vendor_id is required when creating a VENDOR user.",
                )
            v = db.query(Vendor).filter(Vendor.id == req.vendor_id).first()
            if not v:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Vendor with ID {req.vendor_id} does not exist.",
                )

        # Validate CUSTOMER link
        if role_upper == UserRole.CUSTOMER and req.customer_id:
            c = db.query(Customer).filter(Customer.customer_id == req.customer_id).first()
            if not c:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Customer with ID {req.customer_id} does not exist.",
                )

        user = User(
            email=email_clean,
            hashed_password=hash_password(req.password),
            role=role_upper,
            vendor_id=req.vendor_id if role_upper == UserRole.VENDOR else None,
            customer_id=req.customer_id if role_upper == UserRole.CUSTOMER else None,
            is_active=req.is_active,
            is_verified=req.is_verified,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("Admin created user: id=%s email=%s role=%s", user.id, user.email, user.role)
        return user

    @staticmethod
    def admin_list_users(
        db: Session,
        role: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[User]:
        """List users with optional role filtering."""
        query = db.query(User)
        if role:
            query = query.filter(User.role == role.upper())
        return query.order_by(User.id.asc()).offset(skip).limit(limit).all()

    @staticmethod
    def admin_get_user(db: Session, user_id: int) -> User:
        """Fetch single user by ID."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found.",
            )
        return user

    @staticmethod
    def admin_update_user_status(
        db: Session,
        user_id: int,
        req: AdminUpdateUserStatusRequest,
    ) -> User:
        """Update active/verified status of a user."""
        user = AuthService.admin_get_user(db, user_id)
        if req.is_active is not None:
            user.is_active = req.is_active
            if not req.is_active:
                # Deactivating user revokes all active sessions
                AuthService.revoke_all_sessions(db, user.id)
        if req.is_verified is not None:
            user.is_verified = req.is_verified

        user.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def admin_update_user_role(
        db: Session,
        user_id: int,
        req: AdminUpdateUserRoleRequest,
    ) -> User:
        """Update user role and entity linkage."""
        user = AuthService.admin_get_user(db, user_id)
        role_upper = req.role.upper()

        if role_upper not in UserRole.ALL_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role '{req.role}'.",
            )

        if role_upper == UserRole.VENDOR:
            if not req.vendor_id and not user.vendor_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="vendor_id is required for VENDOR role.",
                )
            if req.vendor_id:
                v = db.query(Vendor).filter(Vendor.id == req.vendor_id).first()
                if not v:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Vendor {req.vendor_id} does not exist.",
                    )
                user.vendor_id = req.vendor_id
            user.customer_id = None

        elif role_upper == UserRole.CUSTOMER:
            if req.customer_id:
                c = db.query(Customer).filter(Customer.customer_id == req.customer_id).first()
                if not c:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Customer {req.customer_id} does not exist.",
                    )
                user.customer_id = req.customer_id
            user.vendor_id = None

        elif role_upper == UserRole.ADMIN:
            user.vendor_id = None
            user.customer_id = None

        user.role = role_upper
        user.updated_at = datetime.utcnow()
        # Revoke sessions so user receives new token with updated role
        AuthService.revoke_all_sessions(db, user.id)
        db.commit()
        db.refresh(user)
        return user

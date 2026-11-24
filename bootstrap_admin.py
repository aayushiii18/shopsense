"""
bootstrap_admin.py — Secure administrative bootstrap CLI tool for ShopSense.

Stage 7: Authentication, JWT Security, RBAC & Multi-Tenant Access Control.
Initializes the first administrative account securely and idempotently.

Usage:
    python bootstrap_admin.py --email admin@shopsense.com --password YourSecurePassword123!
    python bootstrap_admin.py  (interactive prompt)
    ADMIN_EMAIL=... ADMIN_PASSWORD=... python bootstrap_admin.py
"""

import argparse
import getpass
import os
import sys
from datetime import datetime

from app.database import SessionLocal
from app.models.user import User, UserRole
from app.core.security import hash_password


def parse_args():
    parser = argparse.ArgumentParser(description="Bootstrap initial ShopSense administrator account.")
    parser.add_argument("--email", "-e", help="Admin email address.", default=None)
    parser.add_argument("--password", "-p", help="Admin password (min 8 characters).", default=None)
    parser.add_argument("--force", "-f", action="store_true", help="Update password if admin already exists.")
    return parser.parse_args()


def bootstrap_admin_user(email: str, password: str, force: bool = False, db=None) -> User:
    """Idempotently bootstrap or update an administrator account."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        email = email.strip().lower()
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            if existing.role != UserRole.ADMIN:
                raise ValueError(f"User {email} already exists with non-admin role '{existing.role}'.")

            if force:
                existing.hashed_password = hash_password(password)
                existing.updated_at = datetime.utcnow()
                db.commit()
                db.refresh(existing)
                print(f"Success: Administrator account '{email}' updated with new credentials.")
                return existing
            else:
                print(f"Administrator account '{email}' already exists. Use --force to update credentials.")
                return existing

        new_admin = User(
            email=email,
            hashed_password=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(new_admin)
        db.commit()
        db.refresh(new_admin)
        print(f"Success: Initial administrator account created successfully (User ID: {new_admin.id}, Email: {new_admin.email}).")
        return new_admin
    except Exception as e:
        db.rollback()
        raise e
    finally:
        if close_db:
            db.close()


def main():
    args = parse_args()

    email = args.email or os.getenv("ADMIN_EMAIL")
    password = args.password or os.getenv("ADMIN_PASSWORD")

    if not email:
        email = input("Enter administrative email: ").strip()

    email = email.strip().lower()
    if not email or "@" not in email:
        print("Error: A valid email address is required.", file=sys.stderr)
        sys.exit(1)

    if not password:
        password = getpass.getpass("Enter administrative password (min 8 characters): ")
        confirm_password = getpass.getpass("Confirm administrative password: ")
        if password != confirm_password:
            print("Error: Passwords do not match.", file=sys.stderr)
            sys.exit(1)

    if len(password) < 8:
        print("Error: Password must be at least 8 characters long.", file=sys.stderr)
        sys.exit(1)

    try:
        bootstrap_admin_user(email=email, password=password, force=args.force)
    except Exception as e:
        print(f"Error during bootstrap: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
app/core/config.py — Centralized configuration settings for ShopSense.

Stage 7: Authentication, JWT Security, RBAC & Multi-Tenant Access Control.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# JWT and Authentication Settings
JWT_SECRET_KEY: str = os.getenv(
    "JWT_SECRET_KEY",
    "shopsense-insecure-default-key-change-in-production-stage7-jwt-secret-token",
)
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Security & Password Configuration
BCRYPT_ROUNDS: int = int(os.getenv("BCRYPT_ROUNDS", "12"))

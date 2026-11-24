"""
backend/config.py — Centralized Production Configuration for ShopSense.

Milestone 4, Step 1: Production Configuration.

Attributes:
- PROJECT_NAME: 'ShopSense'
- VERSION: '1.0.0'
- DATABASE_URL: Loaded from DATABASE_URL environment variable
- FORECAST_MODEL_PATH: 'models/forecast.pkl'
- RECOMMENDATION_MODEL_PATH / RECOMMENDER_MODEL_PATH: 'models/recommender.pkl'
- MAX_RECORDS: 100000
"""

import os
import logging
from typing import Any, Dict, Optional
from dotenv import load_dotenv

# Ensure .env is loaded if present
load_dotenv()

logger = logging.getLogger("backend.config")


class Settings:
    """
    Centralized configuration manager for the ShopSense platform.
    Supports environment variable loading, strict production validation, and multi-environment awareness.
    """

    def __init__(
        self,
        project_name: Optional[str] = None,
        version: Optional[str] = None,
        database_url: Optional[str] = None,
        forecast_model_path: Optional[str] = None,
        recommendation_model_path: Optional[str] = None,
        max_records: Optional[int] = None,
        environment: Optional[str] = None,
        secret_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        mlflow_tracking_uri: Optional[str] = None,
        validate: bool = True,
    ):
        # 1. Environment & Mode
        self.environment = (
            environment
            or os.getenv("ENVIRONMENT")
            or os.getenv("ENV")
            or "development"
        ).strip().lower()

        # 2. Core Project Metadata
        self.project_name = (
            project_name
            if project_name is not None
            else os.getenv("PROJECT_NAME") or "ShopSense"
        ).strip()

        self.version = (
            version
            if version is not None
            else os.getenv("VERSION") or os.getenv("APP_VERSION") or "1.0.0"
        ).strip()

        # 3. Model Paths
        self.forecast_model_path = (
            forecast_model_path
            if forecast_model_path is not None
            else os.getenv("FORECAST_MODEL_PATH") or "models/forecast.pkl"
        ).strip()

        self.recommendation_model_path = (
            recommendation_model_path
            if recommendation_model_path is not None
            else os.getenv("RECOMMENDATION_MODEL_PATH") or os.getenv("RECOMMENDER_MODEL_PATH") or "models/recommender.pkl"
        ).strip()
        self.recommender_model_path = self.recommendation_model_path

        # 4. Record Limits
        raw_max_records = (
            max_records
            if max_records is not None
            else os.getenv("MAX_RECORDS") or os.getenv("MAXIMUM_RECORDS") or 100000
        )
        try:
            self.max_records = int(raw_max_records)
        except (ValueError, TypeError):
            raise ValueError(
                f"Configuration Error: Invalid MAX_RECORDS '{raw_max_records}'. Must be a valid integer."
            )

        # 5. Database URL Resolution
        raw_db_url = database_url if database_url is not None else os.getenv("DATABASE_URL")
        if raw_db_url:
            raw_db_url = raw_db_url.strip()
            # Normalize postgres:// to postgresql:// for modern SQLAlchemy compatibility
            if raw_db_url.startswith("postgres://"):
                raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
        self.database_url = raw_db_url

        # 6. Ancillary System Settings
        self.secret_key = (
            secret_key
            or os.getenv("SECRET_KEY")
            or "shopsense-dev-insecure-key-change-in-production"
        )
        self.api_base_url = (
            api_base_url
            or os.getenv("API_BASE_URL")
            or "http://127.0.0.1:8000"
        ).rstrip("/")
        self.mlflow_tracking_uri = (
            mlflow_tracking_uri
            or os.getenv("MLFLOW_TRACKING_URI")
            or "sqlite:///./mlflow.db"
        )

        # 7. Uppercase property aliases matching specification
        self.PROJECT_NAME = self.project_name
        self.VERSION = self.version
        self.DATABASE_URL = self.database_url
        self.FORECAST_MODEL_PATH = self.forecast_model_path
        self.RECOMMENDATION_MODEL_PATH = self.recommendation_model_path
        self.RECOMMENDER_MODEL_PATH = self.recommender_model_path
        self.MAX_RECORDS = self.max_records
        self.ENVIRONMENT = self.environment

        if validate:
            self.validate()

    def is_production(self) -> bool:
        """Return True if running in a production environment."""
        return self.environment in ("production", "prod")

    def validate(self) -> None:
        """
        Validate all configuration invariants.
        Raises ValueError with clear, actionable diagnostics on invalid settings.
        """
        # Validate Project Name
        if not self.project_name:
            raise ValueError("Configuration Error: 'PROJECT_NAME' cannot be empty.")

        # Validate Version
        if not self.version:
            raise ValueError("Configuration Error: 'VERSION' cannot be empty.")

        # Validate Record Limits
        if self.max_records <= 0:
            raise ValueError(
                f"Configuration Error: 'MAX_RECORDS' must be a positive integer (> 0), got {self.max_records}."
            )

        # Validate Model Paths
        if not self.forecast_model_path:
            raise ValueError("Configuration Error: 'FORECAST_MODEL_PATH' cannot be empty.")
        if not self.recommendation_model_path:
            raise ValueError("Configuration Error: 'RECOMMENDATION_MODEL_PATH' cannot be empty.")

        # Validate Database URL
        if self.is_production():
            if not self.database_url:
                raise ValueError(
                    "Configuration Error: 'DATABASE_URL' environment variable is required in production. "
                    "Silent fallback to SQLite is strictly forbidden in production."
                )
            if self.database_url.startswith("sqlite"):
                raise ValueError(
                    "Configuration Error: SQLite database URL is not permitted in production. "
                    "A production PostgreSQL database URL must be configured via 'DATABASE_URL'."
                )
        else:
            if not self.database_url:
                # In non-production, fallback to SQLite with an explicit warning
                fallback = os.getenv("TEST_DATABASE_URL", "sqlite:///./test_shopsense.db")
                logger.warning(
                    "DATABASE_URL not configured in environment. Using non-production fallback: %s. "
                    "Notice: Silent fallback is disabled in production.",
                    fallback,
                )
                self.database_url = fallback
                self.DATABASE_URL = fallback

    def __getitem__(self, key: str) -> Any:
        """Support dictionary-style access (e.g., settings['DATABASE_URL'])."""
        k = key.lower()
        if hasattr(self, k):
            return getattr(self, k)
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(f"Unknown configuration key: {key}")

    def to_dict(self) -> Dict[str, Any]:
        """Return configuration as a dictionary, masking sensitive credentials."""
        masked_db = self.database_url
        if masked_db and "@" in masked_db:
            prefix = masked_db.split("@")[0]
            host_part = masked_db.split("@")[1]
            if ":" in prefix:
                scheme_user = prefix.rsplit(":", 1)[0]
                masked_db = f"{scheme_user}:******@{host_part}"

        return {
            "PROJECT_NAME": self.project_name,
            "VERSION": self.version,
            "DATABASE_URL": masked_db,
            "FORECAST_MODEL_PATH": self.forecast_model_path,
            "RECOMMENDATION_MODEL_PATH": self.recommendation_model_path,
            "MAX_RECORDS": self.max_records,
            "ENVIRONMENT": self.environment,
            "IS_PRODUCTION": self.is_production(),
        }


# ── Global Singleton & Factory Functions ────────────────────────────────────

_settings_instance: Optional[Settings] = None


def get_settings(reload: bool = False, **kwargs) -> Settings:
    """Return singleton Settings instance, reloading if requested."""
    global _settings_instance
    if _settings_instance is None or reload or kwargs:
        _settings_instance = Settings(**kwargs)
    return _settings_instance


def load_config(reload: bool = False, **kwargs) -> Settings:
    """Alias for get_settings()."""
    return get_settings(reload=reload, **kwargs)


# ── Module-Level Canonical Constants ─────────────────────────────────────────
# Direct imports: from backend.config import PROJECT_NAME, VERSION, ...

PROJECT_NAME = "ShopSense"
VERSION = "1.0.0"
FORECAST_MODEL_PATH = "models/forecast.pkl"
RECOMMENDER_MODEL_PATH = "models/recommender.pkl"
RECOMMENDATION_MODEL_PATH = "models/recommender.pkl"
MAX_RECORDS = 100000

# Resolve active DATABASE_URL from environment or settings
try:
    settings = get_settings()
    DATABASE_URL = settings.database_url
except Exception:
    # Safe fallback if loaded in isolated testing harness with missing required env
    DATABASE_URL = os.getenv("DATABASE_URL")
    settings = None

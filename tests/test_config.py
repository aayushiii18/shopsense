"""
tests/test_config.py — Automated Test Suite for Milestone 4, Step 1: Production Configuration.

Validates:
1. Default configuration values (Project Name, Version, Model Paths, Record Limits).
2. Module-level canonical exports matching specification.
3. Environment variable loading and dynamic overrides.
4. Database URL resolution and postgres:// normalization.
5. Strict production validation (rejection of missing DATABASE_URL and SQLite in production).
6. Clear error messages on invalid or missing required settings.
7. Dictionary-style access and secret masking.
8. app.config proxy compatibility.
9. Application startup and database connection verification.
"""

import os
from unittest import mock
import pytest
from fastapi.testclient import TestClient

from backend.config import (
    Settings,
    get_settings,
    load_config,
    PROJECT_NAME,
    VERSION,
    FORECAST_MODEL_PATH,
    RECOMMENDER_MODEL_PATH,
    RECOMMENDATION_MODEL_PATH,
    MAX_RECORDS,
)
import app.config as app_config
from app.main import app


def test_01_default_configuration_values():
    """Verify default values match Milestone 4 Step 1 specifications."""
    s = Settings(database_url="postgresql://usr:pwd@localhost:5432/testdb", environment="development")
    assert s.project_name == "ShopSense"
    assert s.version == "1.0.0"
    assert s.forecast_model_path == "models/forecast.pkl"
    assert s.recommendation_model_path == "models/recommender.pkl"
    assert s.recommender_model_path == "models/recommender.pkl"
    assert s.max_records == 100000
    assert s.is_production() is False


def test_02_module_level_canonical_constants():
    """Verify module-level exports exist and match specifications."""
    assert PROJECT_NAME == "ShopSense"
    assert VERSION == "1.0.0"
    assert FORECAST_MODEL_PATH == "models/forecast.pkl"
    assert RECOMMENDER_MODEL_PATH == "models/recommender.pkl"
    assert RECOMMENDATION_MODEL_PATH == "models/recommender.pkl"
    assert MAX_RECORDS == 100000


def test_03_environment_variable_overrides():
    """Verify settings can be overridden via environment variables."""
    overrides = {
        "PROJECT_NAME": "ShopSense-Enterprise",
        "VERSION": "2.5.0",
        "FORECAST_MODEL_PATH": "custom/models/forecast_v2.pkl",
        "RECOMMENDATION_MODEL_PATH": "custom/models/recommender_v2.pkl",
        "MAX_RECORDS": "50000",
        "ENVIRONMENT": "staging",
        "DATABASE_URL": "postgresql://custom_user:custom_pass@dbhost:5432/customdb",
    }
    with mock.patch.dict(os.environ, overrides):
        s = Settings()
        assert s.project_name == "ShopSense-Enterprise"
        assert s.version == "2.5.0"
        assert s.forecast_model_path == "custom/models/forecast_v2.pkl"
        assert s.recommendation_model_path == "custom/models/recommender_v2.pkl"
        assert s.max_records == 50000
        assert s.environment == "staging"
        assert s.database_url == "postgresql://custom_user:custom_pass@dbhost:5432/customdb"


def test_04_database_url_postgres_normalization():
    """Verify legacy postgres:// scheme is normalized to modern postgresql://."""
    s = Settings(database_url="postgres://user:pass@host:5432/dbname", environment="development")
    assert s.database_url == "postgresql://user:pass@host:5432/dbname"


def test_05_production_rejects_missing_database_url():
    """
    CRITICAL PRODUCTION INVARIANT:
    In production mode, missing DATABASE_URL must raise ValueError and never silently fall back.
    """
    clean_env = os.environ.copy()
    clean_env.pop("DATABASE_URL", None)
    clean_env["ENVIRONMENT"] = "production"

    with mock.patch.dict(os.environ, clean_env, clear=True):
        with pytest.raises(ValueError) as exc_info:
            Settings(database_url=None, environment="production")
        assert "DATABASE_URL' environment variable is required in production" in str(exc_info.value)
        assert "Silent fallback to SQLite is strictly forbidden" in str(exc_info.value)


def test_06_production_rejects_sqlite_database_url():
    """
    CRITICAL PRODUCTION INVARIANT:
    In production mode, SQLite URLs must be rejected.
    """
    with pytest.raises(ValueError) as exc_info:
        Settings(database_url="sqlite:///./prod.db", environment="production")
    assert "SQLite database URL is not permitted in production" in str(exc_info.value)


def test_07_invalid_max_records_rejection():
    """Verify non-positive and non-integer MAX_RECORDS raise ValueError."""
    with pytest.raises(ValueError) as exc1:
        Settings(database_url="postgresql://u:p@h/d", max_records=0)
    assert "MAX_RECORDS' must be a positive integer" in str(exc1.value)

    with pytest.raises(ValueError) as exc2:
        Settings(database_url="postgresql://u:p@h/d", max_records=-100)
    assert "MAX_RECORDS' must be a positive integer" in str(exc2.value)

    with mock.patch.dict(os.environ, {"MAX_RECORDS": "invalid_number"}):
        with pytest.raises(ValueError) as exc3:
            Settings(database_url="postgresql://u:p@h/d")
        assert "Invalid MAX_RECORDS" in str(exc3.value)


def test_08_empty_project_name_or_version_rejection():
    """Verify empty project name or version raises ValueError."""
    with pytest.raises(ValueError) as exc1:
        Settings(database_url="postgresql://u:p@h/d", project_name="")
    assert "PROJECT_NAME' cannot be empty" in str(exc1.value)

    with pytest.raises(ValueError) as exc2:
        Settings(database_url="postgresql://u:p@h/d", version="")
    assert "VERSION' cannot be empty" in str(exc2.value)


def test_09_dict_style_access_and_secret_masking():
    """Verify dictionary-style access and password masking in to_dict()."""
    s = Settings(
        database_url="postgresql://admin_user:SuperSecretPassword123@db.internal:5432/shopsense_db",
        environment="development",
    )
    assert s["PROJECT_NAME"] == "ShopSense"
    assert s["version"] == "1.0.0"
    assert s["MAX_RECORDS"] == 100000
    assert "SuperSecretPassword123" in s["DATABASE_URL"]

    # Verify to_dict() masks credentials
    d = s.to_dict()
    assert "SuperSecretPassword123" not in d["DATABASE_URL"]
    assert "******" in d["DATABASE_URL"]
    assert "admin_user" in d["DATABASE_URL"]
    assert d["PROJECT_NAME"] == "ShopSense"
    assert d["MAX_RECORDS"] == 100000


def test_10_app_config_proxy_compatibility():
    """Verify app.config exports match backend.config identically."""
    assert app_config.PROJECT_NAME == "ShopSense"
    assert app_config.VERSION == "1.0.0"
    assert app_config.FORECAST_MODEL_PATH == "models/forecast.pkl"
    assert app_config.RECOMMENDER_MODEL_PATH == "models/recommender.pkl"
    assert app_config.MAX_RECORDS == 100000
    assert app_config.settings is not None
    assert app_config.get_settings().project_name == "ShopSense"


def test_11_fastapi_app_startup_metadata():
    """Verify FastAPI application initializes with centralized configuration."""
    s = get_settings()
    assert "ShopSense" in app.title
    assert app.version == s.version

    with TestClient(app) as client:
        # Verify application root/docs endpoint responds
        resp = client.get("/docs")
        assert resp.status_code == 200

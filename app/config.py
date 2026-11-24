"""
app/config.py — Forwarding proxy to backend.config for unified application configuration.
"""

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
    DATABASE_URL,
    settings,
)

__all__ = [
    "Settings",
    "get_settings",
    "load_config",
    "PROJECT_NAME",
    "VERSION",
    "FORECAST_MODEL_PATH",
    "RECOMMENDER_MODEL_PATH",
    "RECOMMENDATION_MODEL_PATH",
    "MAX_RECORDS",
    "DATABASE_URL",
    "settings",
]

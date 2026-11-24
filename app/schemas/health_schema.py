"""
app/schemas/health_schema.py — Pydantic models for Centralized System Health & Integration Status.

Milestone 4 Step 3: Centralized Integration Status Module.
Status Values: HEALTHY, DEGRADED, UNAVAILABLE
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum


class ComponentStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class ComponentHealthResponse(BaseModel):
    """Schema for individual monitored component health."""
    name: str = Field(..., description="Monitored component identifier")
    status: ComponentStatus = Field(..., description="Component state: HEALTHY, DEGRADED, or UNAVAILABLE")
    message: str = Field(..., description="Short diagnostic summary (sanitized of sensitive information)")
    last_checked: str = Field(..., description="ISO 8601 timestamp of diagnostic check")
    latency_ms: Optional[float] = Field(None, description="Diagnostic check response time in milliseconds")
    details: Optional[Dict[str, Any]] = Field(None, description="Non-sensitive operational metadata")


class IntegrationStatusResponse(BaseModel):
    """Comprehensive system-wide integration health status for admin inspection."""
    overall_status: ComponentStatus = Field(..., description="Aggregated platform health status")
    status: str = Field("healthy", description="Backward-compatible health string ('healthy', 'degraded', 'unavailable')")
    database: str = Field("connected", description="Backward-compatible database connectivity string")
    system_name: str = Field("ShopSense", description="Application name")
    version: str = Field("1.0.0", description="Platform release version")
    timestamp: str = Field(..., description="ISO 8601 timestamp of health inspection")
    components: Dict[str, ComponentHealthResponse] = Field(
        ...,
        description="Health states for Database, Sales API, Forecasting API, Recommendation API, MLflow, Workflows, and App",
    )

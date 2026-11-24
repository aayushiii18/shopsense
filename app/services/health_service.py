"""
app/services/health_service.py — Centralized Integration Status & System Health Diagnostics.

Milestone 4, Step 3: Integration Status Module.

Monitors 7 core platform components safely and deterministically:
  1. Database (PostgreSQL / SQLAlchemy connectivity & latency)
  2. Sales API (Route registration & transaction aggregation verification)
  3. Forecasting API (Route registration & forecast model artifact verification)
  4. Recommendation API (Route registration, interaction readiness, & model artifact check)
  5. MLflow (Tracking server connectivity & model registry availability)
  6. Automated Workflows (Scheduler status, last execution time, & latest outcome)
  7. Backend Application (FastAPI service uptime, release metadata, & route registry)

Security & Resilience Guarantees:
  - Never exposes raw connection strings, database credentials, secrets, or stack traces.
  - Strictly enforces lightweight checks with bounded timeouts.
  - Isolates component failures so a single failing dependency never crashes diagnostics.
  - Reports actual runtime state without fabricating execution history or model availability.
"""

import os
import re
import time
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import joblib
import requests
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.customer_interaction import CustomerInteraction
from app.models.product import Product
from app.models.transaction import Transaction
from app.models.workflow_audit import WorkflowAuditLog
from app.schemas.health_schema import ComponentStatus
from backend.config import get_settings

logger = logging.getLogger("shopsense.health")

_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SERVICE_START_TIME = datetime.now(timezone.utc)
_VALIDATED_MODEL_CACHE: Dict[str, tuple[tuple[float, int], Any]] = {}


def _now_iso() -> str:
    """Returns current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _resolve_path(path: str) -> str:
    """Resolves a relative artifact path against the project root."""
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(_ROOT_DIR, path))


def _sanitize_uri(uri: str) -> str:
    """Masks embedded user credentials or full local prefixes from URIs before display."""
    if not uri:
        return "unconfigured"
    masked = re.sub(r"://([^:@/]+):([^@/]+)@", r"://***:***@", uri.strip())
    if masked.startswith("sqlite:///"):
        # Expose only filename / safe relative reference without deep host directories
        raw = masked[len("sqlite:///"):]
        return f"sqlite:///{os.path.basename(raw) or 'mlflow.db'}"
    return masked


def _build_component(
    name: str,
    status: ComponentStatus,
    message: str,
    latency_ms: Optional[float] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "name": name,
        "status": status.value,
        "message": message,
        "last_checked": _now_iso(),
        "latency_ms": round(latency_ms, 2) if latency_ms is not None else None,
        "details": details or {},
    }


def check_database_health(db: Optional[Session]) -> Dict[str, Any]:
    """Check database connectivity via lightweight SELECT 1 probe."""
    t0 = time.perf_counter()
    if db is None:
        return _build_component(
            name="Database",
            status=ComponentStatus.UNAVAILABLE,
            message="Database session unavailable.",
            latency_ms=0.0,
        )
    try:
        db.execute(text("SELECT 1"))
        latency_ms = (time.perf_counter() - t0) * 1000.0
        dialect = "database"
        try:
            bind = db.get_bind()
            if bind is not None and getattr(bind, "dialect", None) is not None:
                dialect = bind.dialect.name.upper()
        except Exception:
            pass

        if latency_ms > 1000.0:
            return _build_component(
                name="Database",
                status=ComponentStatus.DEGRADED,
                message=f"{dialect} connection responding slowly ({latency_ms:.1f} ms).",
                latency_ms=latency_ms,
                details={"dialect": dialect, "connected": True},
            )
        return _build_component(
            name="Database",
            status=ComponentStatus.HEALTHY,
            message=f"{dialect} database connection active ({latency_ms:.1f} ms).",
            latency_ms=latency_ms,
            details={"dialect": dialect, "connected": True},
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        logger.warning("Database health check failed: %s", type(exc).__name__)
        return _build_component(
            name="Database",
            status=ComponentStatus.UNAVAILABLE,
            message="Database connection failed or timed out.",
            latency_ms=latency_ms,
            details={"connected": False, "error_type": type(exc).__name__},
        )


def check_sales_api_health(
    db: Optional[Session],
    route_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Verify Sales API endpoints are registered and sales queries execute."""
    t0 = time.perf_counter()
    required_routes = {"/analytics/revenue", "/analytics/transactions", "/analytics/summary"}
    routes_ok = True
    if route_paths is not None:
        registered = set(route_paths)
        routes_ok = required_routes.issubset(registered)

    if not routes_ok:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return _build_component(
            name="Sales API",
            status=ComponentStatus.UNAVAILABLE,
            message="One or more core Sales API routes are not registered.",
            latency_ms=latency_ms,
            details={"routes_registered": False},
        )

    if db is None:
        return _build_component(
            name="Sales API",
            status=ComponentStatus.UNAVAILABLE,
            message="Sales API cannot query data without an active database session.",
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            details={"routes_registered": routes_ok, "db_query_ok": False},
        )

    try:
        row = (
            db.query(
                func.count(Transaction.transaction_id),
                func.coalesce(func.sum(Transaction.amount), 0.0),
            )
            .first()
        )
        tx_count = int(row[0] or 0) if row else 0
        gmv = round(float(row[1] or 0.0), 2) if row else 0.0
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return _build_component(
            name="Sales API",
            status=ComponentStatus.HEALTHY,
            message=f"Sales API operational ({tx_count} transactions, {gmv:,.2f} GMV).",
            latency_ms=latency_ms,
            details={"routes_registered": routes_ok, "transaction_count": tx_count, "total_gmv": gmv},
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        logger.warning("Sales API health check failed: %s", type(exc).__name__)
        return _build_component(
            name="Sales API",
            status=ComponentStatus.UNAVAILABLE,
            message="Sales API unavailable due to database query failure.",
            latency_ms=latency_ms,
            details={"routes_registered": routes_ok, "error_type": type(exc).__name__},
        )


def check_forecasting_api_health(
    db: Optional[Session],
    route_paths: Optional[List[str]] = None,
    forecast_model_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify Forecasting API routes and forecast model loading status."""
    t0 = time.perf_counter()
    if route_paths is not None and "/forecast/{month}" not in set(route_paths):
        return _build_component(
            name="Forecasting API",
            status=ComponentStatus.UNAVAILABLE,
            message="Forecasting API route (/forecast/{month}) is not registered.",
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            details={"routes_registered": False},
        )

    settings = get_settings()
    configured_rel = (
        forecast_model_path
        if forecast_model_path is not None
        else os.getenv("FORECAST_MODEL_PATH") or settings.forecast_model_path
    ).strip()
    configured_abs = _resolve_path(configured_rel)
    legacy_fallback_rel = "models/inventory_model.pkl"
    legacy_fallback_abs = _resolve_path(legacy_fallback_rel)

    def _validate_model_file(abs_p: str) -> tuple[bool, Optional[str]]:
        try:
            stat = os.stat(abs_p)
            sig = (stat.st_mtime, stat.st_size)
            cached = _VALIDATED_MODEL_CACHE.get(abs_p)
            if cached and cached[0] == sig:
                model = cached[1]
            else:
                model = joblib.load(abs_p)
                _VALIDATED_MODEL_CACHE[abs_p] = (sig, model)
            if not hasattr(model, "predict"):
                _VALIDATED_MODEL_CACHE.pop(abs_p, None)
                return False, "Loaded artifact missing predict() method."
            pred = model.predict([[1]])
            _ = float(pred[0])
            return True, None
        except Exception as exc:
            _VALIDATED_MODEL_CACHE.pop(abs_p, None)
            return False, type(exc).__name__

    # 1. Primary configured path check
    if os.path.exists(configured_abs):
        ok, err = _validate_model_file(configured_abs)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        if ok:
            return _build_component(
                name="Forecasting API",
                status=ComponentStatus.HEALTHY,
                message=f"Forecasting API operational; model loaded from '{configured_rel}'.",
                latency_ms=latency_ms,
                details={
                    "configured_path": configured_rel,
                    "configured_exists": True,
                    "model_loaded": True,
                },
            )
        return _build_component(
            name="Forecasting API",
            status=ComponentStatus.UNAVAILABLE,
            message=f"Forecast model at '{configured_rel}' is invalid or failed to load ({err}).",
            latency_ms=latency_ms,
            details={
                "configured_path": configured_rel,
                "configured_exists": True,
                "model_loaded": False,
                "error_type": err,
            },
        )

    # 2. Default configured path missing -> check legacy fallback only if default configured path
    if configured_rel == "models/forecast.pkl" and os.path.exists(legacy_fallback_abs):
        ok, err = _validate_model_file(legacy_fallback_abs)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        if ok:
            return _build_component(
                name="Forecasting API",
                status=ComponentStatus.DEGRADED,
                message=(
                    f"Configured forecast model missing at '{configured_rel}'; "
                    f"operating via fallback '{legacy_fallback_rel}'."
                ),
                latency_ms=latency_ms,
                details={
                    "configured_path": configured_rel,
                    "configured_exists": False,
                    "fallback_path": legacy_fallback_rel,
                    "fallback_exists": True,
                    "model_loaded": True,
                },
            )

    # 3. Missing configured model file and no valid artifact loaded
    latency_ms = (time.perf_counter() - t0) * 1000.0
    return _build_component(
        name="Forecasting API",
        status=ComponentStatus.UNAVAILABLE,
        message=f"Forecast model file missing at '{configured_rel}'.",
        latency_ms=latency_ms,
        details={
            "configured_path": configured_rel,
            "configured_exists": False,
            "model_loaded": False,
        },
    )


def check_recommendation_api_health(
    db: Optional[Session],
    route_paths: Optional[List[str]] = None,
    recommender_model_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify Recommendation API endpoints, DB interaction readiness, and model file state."""
    t0 = time.perf_counter()
    if route_paths is not None:
        registered = set(route_paths)
        if "/recommendations/popular" not in registered and "/recommend/{customer_id}" not in registered:
            return _build_component(
                name="Recommendation API",
                status=ComponentStatus.UNAVAILABLE,
                message="Recommendation API routes are not registered.",
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                details={"routes_registered": False},
            )

    if db is None:
        return _build_component(
            name="Recommendation API",
            status=ComponentStatus.UNAVAILABLE,
            message="Recommendation API unavailable without an active database session.",
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            details={"db_query_ok": False},
        )

    try:
        prod_count = int(db.query(func.count(Product.id)).scalar() or 0)
        ix_count = int(db.query(func.count(CustomerInteraction.interaction_id)).scalar() or 0)
    except Exception as exc:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        logger.warning("Recommendation API DB check failed: %s", type(exc).__name__)
        return _build_component(
            name="Recommendation API",
            status=ComponentStatus.UNAVAILABLE,
            message="Recommendation API unavailable due to database query failure.",
            latency_ms=latency_ms,
            details={"db_query_ok": False, "error_type": type(exc).__name__},
        )

    settings = get_settings()
    rec_rel = (
        recommender_model_path
        if recommender_model_path is not None
        else os.getenv("RECOMMENDATION_MODEL_PATH")
        or os.getenv("RECOMMENDER_MODEL_PATH")
        or settings.recommendation_model_path
    ).strip()
    rec_abs = _resolve_path(rec_rel)

    if os.path.exists(rec_abs):
        try:
            stat = os.stat(rec_abs)
            sig = (stat.st_mtime, stat.st_size)
            cached = _VALIDATED_MODEL_CACHE.get(rec_abs)
            if cached and cached[0] == sig:
                _ = cached[1]
            else:
                loaded_rec = joblib.load(rec_abs)
                _VALIDATED_MODEL_CACHE[rec_abs] = (sig, loaded_rec)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return _build_component(
                name="Recommendation API",
                status=ComponentStatus.HEALTHY,
                message=f"Recommendation API operational; model artifact loaded from '{rec_rel}'.",
                latency_ms=latency_ms,
                details={
                    "configured_path": rec_rel,
                    "model_file_exists": True,
                    "model_loaded": True,
                    "products": prod_count,
                    "interactions": ix_count,
                },
            )
        except Exception as exc:
            _VALIDATED_MODEL_CACHE.pop(rec_abs, None)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return _build_component(
                name="Recommendation API",
                status=ComponentStatus.UNAVAILABLE,
                message=f"Recommender artifact at '{rec_rel}' is corrupted or failed to load.",
                latency_ms=latency_ms,
                details={
                    "configured_path": rec_rel,
                    "model_file_exists": True,
                    "model_loaded": False,
                    "error_type": type(exc).__name__,
                },
            )

    # Dynamic in-memory CF / TF-IDF engine operates when serialized .pkl is missing
    latency_ms = (time.perf_counter() - t0) * 1000.0
    return _build_component(
        name="Recommendation API",
        status=ComponentStatus.DEGRADED,
        message=(
            f"Recommendation API serving via dynamic CF/TF-IDF engine ({ix_count} interactions); "
            f"serialized artifact missing at '{rec_rel}'."
        ),
        latency_ms=latency_ms,
        details={
            "configured_path": rec_rel,
            "model_file_exists": False,
            "engine_mode": "dynamic_in_memory",
            "products": prod_count,
            "interactions": ix_count,
        },
    )


def check_mlflow_health(
    tracking_uri: Optional[str] = None,
    timeout_seconds: float = 2.0,
) -> Dict[str, Any]:
    """Verify MLflow tracking server connectivity and model registry availability."""
    t0 = time.perf_counter()
    settings = get_settings()
    raw_uri = (
        tracking_uri
        if tracking_uri is not None
        else os.getenv("MLFLOW_TRACKING_URI") or settings.mlflow_tracking_uri or ""
    ).strip()
    safe_uri = _sanitize_uri(raw_uri)

    if not raw_uri:
        return _build_component(
            name="MLflow",
            status=ComponentStatus.UNAVAILABLE,
            message="MLflow tracking URI is not configured.",
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            details={"configured": False},
        )

    # 1. Remote HTTP tracking server check (lightweight timeout-bounded HTTP probe)
    if raw_uri.startswith(("http://", "https://")):
        base = raw_uri.rstrip("/")
        try:
            exp_resp = requests.get(
                f"{base}/api/2.0/mlflow/experiments/search?max_results=1",
                timeout=timeout_seconds,
            )
            if exp_resp.status_code == 404:
                # Older MLflow endpoint fallback
                exp_resp = requests.get(f"{base}/health", timeout=timeout_seconds)

            if exp_resp.status_code >= 400:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                return _build_component(
                    name="MLflow",
                    status=ComponentStatus.UNAVAILABLE,
                    message=f"MLflow tracking server returned HTTP {exp_resp.status_code}.",
                    latency_ms=latency_ms,
                    details={"tracking_uri": safe_uri, "http_status": exp_resp.status_code},
                )

            reg_resp = requests.get(
                f"{base}/api/2.0/mlflow/registered-models/search?max_results=1",
                timeout=timeout_seconds,
            )
            latency_ms = (time.perf_counter() - t0) * 1000.0
            if reg_resp.status_code == 200:
                return _build_component(
                    name="MLflow",
                    status=ComponentStatus.HEALTHY,
                    message=f"MLflow tracking server and model registry reachable ({safe_uri}).",
                    latency_ms=latency_ms,
                    details={"tracking_uri": safe_uri, "registry_available": True},
                )
            return _build_component(
                name="MLflow",
                status=ComponentStatus.DEGRADED,
                message=f"MLflow tracking reachable ({safe_uri}), but model registry unavailable.",
                latency_ms=latency_ms,
                details={"tracking_uri": safe_uri, "registry_available": False},
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.warning("MLflow HTTP check failed: %s", type(exc).__name__)
            return _build_component(
                name="MLflow",
                status=ComponentStatus.UNAVAILABLE,
                message=f"MLflow tracking server unreachable at {safe_uri}.",
                latency_ms=latency_ms,
                details={"tracking_uri": safe_uri, "error_type": type(exc).__name__},
            )

    # 2. Local SQLite MLflow backend check (avoids slow cold mlflow import while querying real schema)
    if raw_uri.startswith("sqlite:///"):
        raw_path = raw_uri[len("sqlite:///"):]
        abs_db = _resolve_path(raw_path)
        if not os.path.exists(abs_db):
            return _build_component(
                name="MLflow",
                status=ComponentStatus.UNAVAILABLE,
                message=f"MLflow SQLite store missing at '{safe_uri}'.",
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                details={"tracking_uri": safe_uri, "store_exists": False},
            )
        try:
            conn = sqlite3.connect(f"file:{abs_db}?mode=ro", uri=True, timeout=timeout_seconds)
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM experiments")
                exp_count = int(cur.fetchone()[0])
                try:
                    cur.execute("SELECT COUNT(*) FROM registered_models")
                    rm_count = int(cur.fetchone()[0])
                    registry_ok = True
                except sqlite3.OperationalError:
                    rm_count = 0
                    registry_ok = False
            finally:
                conn.close()

            latency_ms = (time.perf_counter() - t0) * 1000.0
            if registry_ok:
                return _build_component(
                    name="MLflow",
                    status=ComponentStatus.HEALTHY,
                    message=(
                        f"MLflow local tracking and model registry active "
                        f"({exp_count} experiments, {rm_count} registered models)."
                    ),
                    latency_ms=latency_ms,
                    details={
                        "tracking_uri": safe_uri,
                        "experiments_count": exp_count,
                        "registered_models_count": rm_count,
                        "registry_available": True,
                    },
                )
            return _build_component(
                name="MLflow",
                status=ComponentStatus.DEGRADED,
                message=f"MLflow tracking active ({exp_count} experiments), model registry schema absent.",
                latency_ms=latency_ms,
                details={
                    "tracking_uri": safe_uri,
                    "experiments_count": exp_count,
                    "registry_available": False,
                },
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.warning("MLflow SQLite check failed: %s", type(exc).__name__)
            return _build_component(
                name="MLflow",
                status=ComponentStatus.UNAVAILABLE,
                message=f"MLflow SQLite tracking store inaccessible ({safe_uri}).",
                latency_ms=latency_ms,
                details={"tracking_uri": safe_uri, "error_type": type(exc).__name__},
            )

    # 3. Local filesystem store
    local_dir = raw_uri[len("file://"):] if raw_uri.startswith("file://") else raw_uri
    abs_dir = _resolve_path(local_dir.lstrip("/") if os.name == "nt" and local_dir.startswith("/") else local_dir)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    if os.path.isdir(abs_dir):
        return _build_component(
            name="MLflow",
            status=ComponentStatus.DEGRADED,
            message="MLflow file-based artifact store accessible; model registry requires SQL/HTTP store.",
            latency_ms=latency_ms,
            details={"tracking_uri": safe_uri, "registry_available": False},
        )
    return _build_component(
        name="MLflow",
        status=ComponentStatus.UNAVAILABLE,
        message=f"MLflow tracking location unavailable ({safe_uri}).",
        latency_ms=latency_ms,
        details={"tracking_uri": safe_uri},
    )


def check_workflows_health(db: Optional[Session]) -> Dict[str, Any]:
    """Inspect APScheduler active state and genuine workflow audit execution logs."""
    t0 = time.perf_counter()
    from app import scheduler as app_scheduler

    try:
        scheduler_running = bool(app_scheduler.is_scheduler_running())
        jobs_list = app_scheduler.get_scheduled_jobs() if scheduler_running else []
    except Exception:
        scheduler_running = False
        jobs_list = []

    if db is None:
        return _build_component(
            name="Automated Workflows",
            status=ComponentStatus.UNAVAILABLE,
            message="Workflow audit log unavailable due to missing database session.",
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            details={"scheduler_running": scheduler_running, "last_execution": None, "latest_result": None},
        )

    try:
        latest_log = (
            db.query(WorkflowAuditLog)
            .order_by(WorkflowAuditLog.start_time.desc())
            .first()
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0

        last_exec = latest_log.start_time.isoformat() if latest_log and latest_log.start_time else None
        latest_res = latest_log.status if latest_log else "NO_RUNS_RECORDED"
        run_id = latest_log.run_id if latest_log else None
        duration_sec = latest_log.duration_seconds if latest_log else None

        details = {
            "scheduler_running": scheduler_running,
            "scheduled_jobs": len(jobs_list),
            "last_run_id": run_id,
            "last_execution": last_exec,
            "latest_result": latest_res,
            "duration_seconds": duration_sec,
        }

        if latest_log and latest_res == "FAILED":
            return _build_component(
                name="Automated Workflows",
                status=ComponentStatus.DEGRADED,
                message=(
                    f"Scheduler {'ACTIVE' if scheduler_running else 'INACTIVE'}; "
                    f"latest workflow execution FAILED ({last_exec})."
                ),
                latency_ms=latency_ms,
                details=details,
            )

        if not scheduler_running:
            msg_exec = f"Last run: {latest_res} at {last_exec}." if last_exec else "No recorded runs yet."
            return _build_component(
                name="Automated Workflows",
                status=ComponentStatus.DEGRADED,
                message=f"Background scheduler is INACTIVE in this worker process. {msg_exec}",
                latency_ms=latency_ms,
                details=details,
            )

        msg_exec = f"Last run: {latest_res} at {last_exec}." if last_exec else "Standby (no historical runs yet)."
        return _build_component(
            name="Automated Workflows",
            status=ComponentStatus.HEALTHY,
            message=f"Scheduler ACTIVE ({len(jobs_list)} jobs). {msg_exec}",
            latency_ms=latency_ms,
            details=details,
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        logger.warning("Workflows health check failed: %s", type(exc).__name__)
        return _build_component(
            name="Automated Workflows",
            status=ComponentStatus.UNAVAILABLE,
            message="Failed to inspect automated workflow execution history.",
            latency_ms=latency_ms,
            details={"scheduler_running": scheduler_running, "error_type": type(exc).__name__},
        )


def check_backend_application_health(route_paths: Optional[List[str]] = None) -> Dict[str, Any]:
    """Verify FastAPI application runtime configuration and route availability."""
    t0 = time.perf_counter()
    settings = get_settings()
    uptime_seconds = round((datetime.now(timezone.utc) - _SERVICE_START_TIME).total_seconds(), 2)
    route_count = len(route_paths) if route_paths is not None else None
    latency_ms = (time.perf_counter() - t0) * 1000.0

    return _build_component(
        name="Backend Application",
        status=ComponentStatus.HEALTHY,
        message=f"{settings.project_name} Analytics Platform v{settings.version} operational.",
        latency_ms=latency_ms,
        details={
            "project_name": settings.project_name,
            "version": settings.version,
            "environment": settings.environment,
            "uptime_seconds": uptime_seconds,
            "registered_routes": route_count,
        },
    )


def get_system_health(
    db: Optional[Session],
    route_paths: Optional[List[str]] = None,
    forecast_model_path: Optional[str] = None,
    recommender_model_path: Optional[str] = None,
    mlflow_tracking_uri: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Aggregates diagnostic checks across all 7 platform components safely.
    Failure of one check never aborts checks on remaining components.
    """
    settings = get_settings()

    components: Dict[str, Dict[str, Any]] = {}
    check_fns = [
        ("database", lambda: check_database_health(db)),
        ("sales_api", lambda: check_sales_api_health(db, route_paths=route_paths)),
        (
            "forecasting_api",
            lambda: check_forecasting_api_health(
                db, route_paths=route_paths, forecast_model_path=forecast_model_path
            ),
        ),
        (
            "recommendation_api",
            lambda: check_recommendation_api_health(
                db, route_paths=route_paths, recommender_model_path=recommender_model_path
            ),
        ),
        ("mlflow", lambda: check_mlflow_health(tracking_uri=mlflow_tracking_uri)),
        ("automated_workflows", lambda: check_workflows_health(db)),
        ("backend_application", lambda: check_backend_application_health(route_paths=route_paths)),
    ]

    for key, fn in check_fns:
        try:
            components[key] = fn()
        except Exception as exc:
            logger.error("Unexpected failure running health check '%s': %s", key, type(exc).__name__)
            components[key] = _build_component(
                name=key.replace("_", " ").title(),
                status=ComponentStatus.UNAVAILABLE,
                message="Health check encountered an unexpected error.",
                details={"error_type": type(exc).__name__},
            )

    statuses = {k: c["status"] for k, c in components.items()}

    # Critical core outage -> overall UNAVAILABLE
    if (
        statuses.get("database") == ComponentStatus.UNAVAILABLE.value
        or statuses.get("backend_application") == ComponentStatus.UNAVAILABLE.value
    ):
        overall = ComponentStatus.UNAVAILABLE
    elif any(
        s in (ComponentStatus.DEGRADED.value, ComponentStatus.UNAVAILABLE.value)
        for s in statuses.values()
    ):
        overall = ComponentStatus.DEGRADED
    else:
        overall = ComponentStatus.HEALTHY

    return {
        "overall_status": overall.value,
        "status": overall.value.lower(),
        "database": "connected" if statuses.get("database") == ComponentStatus.HEALTHY.value else "disconnected",
        "system_name": settings.project_name,
        "version": settings.version,
        "timestamp": _now_iso(),
        "components": components,
    }

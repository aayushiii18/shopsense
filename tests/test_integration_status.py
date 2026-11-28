"""
tests/test_integration_status.py — Comprehensive verification suite for Milestone 4 Step 3.

Covers:
  1. All 7 monitored components reporting structured HEALTHY, DEGRADED, and UNAVAILABLE states.
  2. Distinction between /health/live (liveness), /health/ready (readiness), and /admin/health (admin diagnostics).
  3. Role-based access control restricting /admin/health exclusively to ADMIN users.
  4. Database disconnection handling without 500 crashes or secret leakage.
  5. Missing & corrupted forecast/recommender model files reported accurately.
  6. MLflow connectivity & registry unavailability handling with timeouts and credential masking.
  7. Scheduler running state & authentic workflow audit log execution history (no fabrication).
  8. Streamlit dashboard Integration Status rendering across component states and roles.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import joblib
import pytest
from sklearn.dummy import DummyRegressor
from sqlalchemy.exc import OperationalError

from app.core.security import create_access_token
from app.models.product import Product
from app.models.vendor import Vendor
from app.models.transaction import Transaction
from app.models.customer import Customer
from app.models.customer_interaction import CustomerInteraction
from app.models.user import User
from app.models.workflow_audit import WorkflowAuditLog
from app.services import health_service


def _create_user_headers(db_session, email: str, role: str, vendor_id=None, customer_id=None) -> dict:
    user = db_session.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            hashed_password="test_hashed_pw_step3",
            role=role,
            vendor_id=vendor_id,
            customer_id=customer_id,
            is_active=True,
            is_verified=True,
            token_version=1,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=role,
        vendor_id=vendor_id,
        customer_id=customer_id,
        token_version=user.token_version or 1,
    )
    return {"Authorization": f"Bearer {token}", "X-Enforce-Auth": "true"}


def test_01_liveness_and_readiness_probes(client, db_session):
    """Verify /health/live and /health/ready behavior cleanly distinguish liveness vs readiness."""
    resp_live = client.get("/health/live")
    assert resp_live.status_code == 200
    live_data = resp_live.json()
    assert live_data["status"] == "UP"
    assert "timestamp" in live_data
    # Liveness must not leak component diagnostics or internal configuration
    assert "components" not in live_data

    resp_ready = client.get("/health/ready")
    assert resp_ready.status_code == 200
    ready_data = resp_ready.json()
    assert ready_data["status"] == "READY"
    assert ready_data["database"] == "HEALTHY"


def test_02_readiness_probe_on_database_disconnection(client):
    """Verify /health/ready fails gracefully with 503 NOT_READY when DB connection drops."""
    with patch("app.services.health_service.check_database_health") as mock_db_check:
        mock_db_check.return_value = {
            "name": "Database",
            "status": "UNAVAILABLE",
            "message": "Database connection failed or timed out.",
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "latency_ms": 5.0,
            "details": {"connected": False},
        }
        resp = client.get("/health/ready")
        assert resp.status_code == 503
        detail = resp.json()["detail"]
        assert detail["status"] == "NOT_READY"
        assert detail["database"] == "UNAVAILABLE"


def test_03_admin_health_rbac_authorization(client, db_session):
    """Verify unauthorized, VENDOR, and CUSTOMER users cannot access /admin/health diagnostics."""
    # Unauthenticated with enforcement
    resp_unauth = client.get("/admin/health", headers={"X-Enforce-Auth": "true"})
    assert resp_unauth.status_code == 401

    # CUSTOMER blocked with 403
    cust_headers = _create_user_headers(db_session, "cust_health@test.local", "CUSTOMER", customer_id=1)
    resp_cust = client.get("/admin/health", headers=cust_headers)
    assert resp_cust.status_code == 403

    # VENDOR blocked with 403
    vend_headers = _create_user_headers(db_session, "vend_health@test.local", "VENDOR", vendor_id=1)
    resp_vend = client.get("/admin/health", headers=vend_headers)
    assert resp_vend.status_code == 403

    # ADMIN succeeds with full 7-component breakdown
    admin_headers = _create_user_headers(db_session, "admin_health@test.local", "ADMIN")
    resp_admin = client.get("/admin/health", headers=admin_headers)
    assert resp_admin.status_code == 200
    data = resp_admin.json()
    assert data["overall_status"] in ("HEALTHY", "DEGRADED", "UNAVAILABLE")
    assert set(data["components"].keys()) == {
        "database",
        "sales_api",
        "forecasting_api",
        "recommendation_api",
        "mlflow",
        "automated_workflows",
        "backend_application",
    }
    for comp in data["components"].values():
        assert comp["status"] in ("HEALTHY", "DEGRADED", "UNAVAILABLE")
        assert comp["name"]
        assert comp["message"]
        assert comp["last_checked"]


def test_04_all_components_healthy_scenario(tmp_path, db_session):
    """Verify overall HEALTHY status when all 7 components pass real verification."""
    # Seed minimal DB records
    v = Vendor(name="Health Vendor", email="hv@test.com", phone="1234567890")
    db_session.add(v)
    db_session.flush()
    p = Product(name="Health Product", price=99.0, vendor_id=v.id)
    db_session.add(p)
    c = Customer(name="Health Cust", email="hc@test.com")
    db_session.add(c)
    db_session.flush()
    db_session.add(Transaction(product_id=p.id, vendor_id=v.id, customer_id=c.customer_id, quantity=2, unit_price=99.0, amount=198.0))
    db_session.add(CustomerInteraction(customer_id=c.customer_id, product_id=p.id, interaction_type="purchase", interaction_weight=3.0))
    db_session.add(
        WorkflowAuditLog(
            run_id="pipeline-healthy-001",
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            duration_seconds=1.2,
            status="SUCCESS",
            total_rows_processed=10,
        )
    )
    db_session.commit()

    # Create valid dummy forecast & recommender joblib artifacts
    forecast_pkl = tmp_path / "forecast.pkl"
    dummy_rf = DummyRegressor(strategy="mean").fit([[1], [2]], [10, 20])
    joblib.dump(dummy_rf, forecast_pkl)

    rec_pkl = tmp_path / "recommender.pkl"
    joblib.dump({"similarity": {1: {1: 1.0}}}, rec_pkl)

    # Create minimal MLflow SQLite store with experiments & registered_models tables
    import sqlite3
    mlflow_db = tmp_path / "test_mlflow.db"
    conn = sqlite3.connect(mlflow_db)
    conn.execute("CREATE TABLE experiments (experiment_id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO experiments VALUES (1, 'Default')")
    conn.execute("CREATE TABLE registered_models (name TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO registered_models VALUES ('InventoryForecast')")
    conn.commit()
    conn.close()

    route_paths = [
        "/analytics/revenue",
        "/analytics/transactions",
        "/analytics/summary",
        "/forecast/{month}",
        "/recommendations/popular",
        "/recommend/{customer_id}",
    ]

    with patch("app.scheduler.is_scheduler_running", return_value=True), \
         patch("app.scheduler.get_scheduled_jobs", return_value=[{"id": "pipeline_job"}, {"id": "mart_job"}]):
        report = health_service.get_system_health(
            db=db_session,
            route_paths=route_paths,
            forecast_model_path=str(forecast_pkl),
            recommender_model_path=str(rec_pkl),
            mlflow_tracking_uri=f"sqlite:///{mlflow_db.as_posix()}",
        )

    assert report["overall_status"] == "HEALTHY"
    assert report["status"] == "healthy"
    assert report["database"] == "connected"
    for key, comp in report["components"].items():
        assert comp["status"] == "HEALTHY", f"Expected {key} HEALTHY, got {comp}"


def test_05_database_disconnection_no_crash_and_no_secret_leak():
    """Verify DB failure reports UNAVAILABLE safely without crashing or leaking connection strings/passwords."""
    broken_db = MagicMock()
    secret_dsn = "postgresql://admin:SuperSecretPass99@prod-db.internal:5432/shopsense"
    broken_db.execute.side_effect = OperationalError(
        "SELECT 1", {}, Exception(f"could not connect to server at {secret_dsn}")
    )
    broken_db.query.side_effect = OperationalError(
        "SELECT *", {}, Exception(f"connection refused: {secret_dsn}")
    )

    report = health_service.get_system_health(
        db=broken_db,
        mlflow_tracking_uri="http://127.0.0.1:59998",
    )

    assert report["overall_status"] == "UNAVAILABLE"
    assert report["status"] == "unavailable"
    assert report["database"] == "disconnected"
    assert report["components"]["database"]["status"] == "UNAVAILABLE"
    assert report["components"]["sales_api"]["status"] == "UNAVAILABLE"
    assert report["components"]["recommendation_api"]["status"] == "UNAVAILABLE"
    assert report["components"]["automated_workflows"]["status"] == "UNAVAILABLE"
    # Backend application stays HEALTHY even when DB is down
    assert report["components"]["backend_application"]["status"] == "HEALTHY"

    # Security verification: credentials & connection strings MUST NEVER appear anywhere in response
    serialized = str(report)
    assert "SuperSecretPass99" not in serialized
    assert "prod-db.internal" not in serialized
    assert "postgresql://" not in serialized


def test_06_missing_and_corrupt_model_files_reported_accurately(tmp_path, db_session):
    """Verify missing or corrupt model files are detected accurately instead of faking HEALTHY."""
    missing_forecast = tmp_path / "does_not_exist_forecast.pkl"
    missing_rec = tmp_path / "does_not_exist_rec.pkl"

    f_res = health_service.check_forecasting_api_health(
        db=db_session,
        forecast_model_path=str(missing_forecast),
    )
    assert f_res["status"] == "UNAVAILABLE"
    assert "missing" in f_res["message"].lower()
    assert f_res["details"]["model_loaded"] is False

    r_res = health_service.check_recommendation_api_health(
        db=db_session,
        recommender_model_path=str(missing_rec),
    )
    # Operates via dynamic CF/TF-IDF when DB works, accurately flagged as DEGRADED due to missing .pkl
    assert r_res["status"] == "DEGRADED"
    assert r_res["details"]["model_file_exists"] is False

    # Now test corrupt model files
    corrupt_forecast = tmp_path / "corrupt_forecast.pkl"
    corrupt_forecast.write_text("not a pickle binary!")
    f_corrupt = health_service.check_forecasting_api_health(
        db=db_session,
        forecast_model_path=str(corrupt_forecast),
    )
    assert f_corrupt["status"] == "UNAVAILABLE"

    corrupt_rec = tmp_path / "corrupt_rec.pkl"
    corrupt_rec.write_bytes(b"\x00\x01corrupt_data")
    r_corrupt = health_service.check_recommendation_api_health(
        db=db_session,
        recommender_model_path=str(corrupt_rec),
    )
    assert r_corrupt["status"] == "UNAVAILABLE"


def test_07_mlflow_unavailability_and_secret_sanitization(tmp_path):
    """Verify MLflow HTTP unreachable, missing SQLite, registry partial degradation, and URI masking."""
    # Unreachable HTTP server with credentials in URL -> UNAVAILABLE and sanitized
    res_http = health_service.check_mlflow_health(
        tracking_uri="http://mluser:mlsecret@127.0.0.1:59997",
        timeout_seconds=0.5,
    )
    assert res_http["status"] == "UNAVAILABLE"
    assert "mlsecret" not in str(res_http)
    assert "mluser" not in str(res_http)

    # Missing SQLite file -> UNAVAILABLE
    res_missing = health_service.check_mlflow_health(
        tracking_uri=f"sqlite:///{(tmp_path / 'absent_mlflow.db').as_posix()}"
    )
    assert res_missing["status"] == "UNAVAILABLE"

    # Mock HTTP 200 experiments + 500 registry -> DEGRADED
    with patch("app.services.health_service.requests.get") as mock_get:
        exp_resp = MagicMock(status_code=200)
        reg_resp = MagicMock(status_code=503)
        mock_get.side_effect = [exp_resp, reg_resp]
        res_partial = health_service.check_mlflow_health(tracking_uri="http://mlflow.local:5000")
        assert res_partial["status"] == "DEGRADED"
        assert res_partial["details"]["registry_available"] is False


def test_08_workflows_status_and_honest_execution_history(db_session):
    """Verify workflow monitor reports exact scheduler state and genuine audit log history."""
    # Empty audit logs + inactive scheduler -> DEGRADED, NO_RUNS_RECORDED (never fabricated)
    with patch("app.scheduler.is_scheduler_running", return_value=False):
        empty_wf = health_service.check_workflows_health(db_session)
    assert empty_wf["status"] == "DEGRADED"
    assert empty_wf["details"]["scheduler_running"] is False
    assert empty_wf["details"]["last_execution"] is None
    assert empty_wf["details"]["latest_result"] == "NO_RUNS_RECORDED"

    # Failed workflow execution recorded -> DEGRADED even if scheduler running
    db_session.add(
        WorkflowAuditLog(
            run_id="pipeline-failed-test",
            start_time=datetime(2026, 11, 24, 12, 0, 0),
            status="FAILED",
            total_rows_processed=0,
        )
    )
    db_session.commit()

    with patch("app.scheduler.is_scheduler_running", return_value=True), \
         patch("app.scheduler.get_scheduled_jobs", return_value=[{"id": "pipeline_job"}, {"id": "mart_job"}]):
        failed_wf = health_service.check_workflows_health(db_session)
    assert failed_wf["status"] == "DEGRADED"
    assert failed_wf["details"]["latest_result"] == "FAILED"
    assert failed_wf["details"]["last_run_id"] == "pipeline-failed-test"


def test_09_streamlit_dashboard_integration_status_and_rbac():
    """Verify Login gate blocks unauthenticated access and Admin Integration Status enforces RBAC."""
    from streamlit.testing.v1 import AppTest

    # Unauthenticated landing must enforce Login Page First with zero dashboard module access
    at_unauth = AppTest.from_file("dashboard/dashboard.py").run(timeout=60)
    assert len(at_unauth.exception) == 0
    assert len(at_unauth.radio) == 0
    assert "Welcome to ShopSense" in "\n".join(m.value for m in at_unauth.markdown)

    # Authenticate as ADMIN and switch to dedicated Integration Status page
    at = AppTest.from_file("dashboard/dashboard.py")
    at.session_state["auth_user"] = {"id": 1, "email": "admin@shopsense.com", "role": "ADMIN"}
    at.run(timeout=60)
    assert len(at.exception) == 0

    at.radio[0].set_value("🩺 Integration Status / System Health").run(timeout=60)
    assert len(at.exception) == 0
    assert any("Refresh Health" in b.label for b in at.button)

    # Confirm 7 components displayed in diagnostics dataframe
    assert len(at.dataframe) >= 1
    df_status = at.dataframe[-1].value
    assert len(df_status) == 7
    assert set(df_status["Component"].tolist()) == {
        "Database",
        "Sales API",
        "Forecasting API",
        "Recommendation API",
        "MLflow",
        "Automated Workflows",
        "Backend Application",
    }

    # Verify VENDOR role does NOT get Integration Status navigation item or panel
    at_vendor = AppTest.from_file("dashboard/dashboard.py")
    at_vendor.session_state["auth_user"] = {"id": 2, "email": "vendor@test.com", "role": "VENDOR", "vendor_id": 1}
    at_vendor.run(timeout=60)
    assert len(at_vendor.exception) == 0
    vendor_nav_options = at_vendor.radio[0].options
    assert "🩺 Integration Status / System Health" not in vendor_nav_options

    # Verify CUSTOMER role does NOT get Integration Status navigation item or panel
    at_cust = AppTest.from_file("dashboard/dashboard.py")
    at_cust.session_state["auth_user"] = {"id": 3, "email": "cust@test.com", "role": "CUSTOMER", "customer_id": 1}
    at_cust.run(timeout=60)
    assert len(at_cust.exception) == 0
    assert "🩺 Integration Status / System Health" not in at_cust.radio[0].options


def test_10_streamlit_dashboard_all_component_states():
    """Verify Streamlit Integration Status renders Green (HEALTHY), Yellow (DEGRADED), and Red (UNAVAILABLE) states."""
    from streamlit.testing.v1 import AppTest

    now_iso = datetime.now(timezone.utc).isoformat()
    mixed_report = {
        "overall_status": "UNAVAILABLE",
        "status": "unavailable",
        "database": "disconnected",
        "system_name": "ShopSense",
        "version": "1.0.0",
        "timestamp": now_iso,
        "components": {
            "database": {"name": "Database", "status": "UNAVAILABLE", "message": "DB connection lost", "last_checked": now_iso, "latency_ms": 5.0, "details": {}},
            "sales_api": {"name": "Sales API", "status": "UNAVAILABLE", "message": "DB unavailable", "last_checked": now_iso, "latency_ms": 1.0, "details": {}},
            "forecasting_api": {"name": "Forecasting API", "status": "DEGRADED", "message": "Using fallback model", "last_checked": now_iso, "latency_ms": 3.0, "details": {"configured_path": "models/forecast.pkl"}},
            "recommendation_api": {"name": "Recommendation API", "status": "HEALTHY", "message": "Model loaded", "last_checked": now_iso, "latency_ms": 2.0, "details": {"configured_path": "models/recommender.pkl"}},
            "mlflow": {"name": "MLflow", "status": "HEALTHY", "message": "Connected", "last_checked": now_iso, "latency_ms": 4.0, "details": {"experiments_count": 2, "registered_models_count": 1}},
            "automated_workflows": {"name": "Automated Workflows", "status": "DEGRADED", "message": "Scheduler stopped", "last_checked": now_iso, "latency_ms": 1.0, "details": {"scheduler_running": False, "latest_result": "NO_RUNS_RECORDED", "last_execution": None}},
            "backend_application": {"name": "Backend Application", "status": "HEALTHY", "message": "FastAPI operational", "last_checked": now_iso, "latency_ms": 0.1, "details": {}},
        },
    }

    with patch("app.services.health_service.get_system_health", return_value=mixed_report):
        at = AppTest.from_file("dashboard/dashboard.py")
        at.session_state["auth_user"] = {"id": 1, "email": "admin@shopsense.com", "role": "ADMIN"}
        at.run(timeout=60)
        at.radio[0].set_value("🩺 Integration Status / System Health").run(timeout=60)
        assert len(at.exception) == 0

        # Confirm metric counts reflect 3 Healthy / 2 Degraded / 2 Down
        metric_vals = [f"{m.label}: {m.value}" for m in at.metric]
        assert any("3 / 7" in mv for mv in metric_vals), f"Metrics were: {metric_vals}"
        assert any("2 Degraded / 2 Down" in mv for mv in metric_vals), f"Metrics were: {metric_vals}"

        # Confirm green, yellow, red visual indicators appear in rendered markdown
        all_md = "\n".join(m.value for m in at.markdown)
        assert "🟢 HEALTHY" in all_md
        assert "🟡 DEGRADED" in all_md
        assert "🔴 UNAVAILABLE" in all_md
        assert "badge-healthy" in all_md
        assert "badge-warning" in all_md
        assert "badge-critical" in all_md


def test_11_version_caption_consistency_and_no_v2_mismatch():
    """Verify DEF-UAT-03 remediation: dashboard sidebar version matches backend 1.0.0 cleanly."""
    from streamlit.testing.v1 import AppTest
    from backend.config import get_settings

    expected_ver = get_settings().version
    at = AppTest.from_file("dashboard/dashboard.py")
    at.session_state["auth_user"] = {"id": 1, "email": "admin@shopsense.com", "role": "ADMIN"}
    at.run(timeout=60)
    assert len(at.exception) == 0

    captions = "\n".join(c.value for c in at.caption)
    assert f"ShopSense v{expected_ver}" in captions
    assert "ShopSense v2.0" not in captions


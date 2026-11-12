"""
tests/test_scheduler_pipeline.py — Test Suite for APScheduler & Analytical Pipeline.

Tests:
  1. Scheduler initialization and safe shutdown.
  2. Duplicate scheduler prevention (singleton guard & double-start safety).
  3. Job configuration (2:00 AM daily cron trigger verification).
  4. Manual pipeline execution (full end-to-end task orchestration).
  5. Individual task breakdown & row processing verification.
  6. Audit persistence (WorkflowAuditLog record in database).
  7. Partial failure handling (failed task marks pipeline as PARTIAL, never SUCCESS).
  8. Total failure handling (all failed tasks mark pipeline as FAILED).
  9. Audit query functions and API endpoints (/analytics/pipeline/audit, /analytics/pipeline/run).
"""

import pytest
from unittest.mock import patch, MagicMock
from apscheduler.triggers.cron import CronTrigger

from app.scheduler import (
    get_scheduler,
    is_scheduler_running,
    start_scheduler,
    stop_scheduler,
    get_scheduled_jobs,
    run_analytical_pipeline,
    get_workflow_audit_logs,
)
from app.models.workflow_audit import WorkflowAuditLog


def test_scheduler_lifecycle():
    """Verify start_scheduler and stop_scheduler lifecycle."""
    stop_scheduler(wait=False)
    assert not is_scheduler_running()

    started = start_scheduler(hour=2, minute=0, enable_flag=True)
    assert started is True
    assert is_scheduler_running()

    jobs = get_scheduled_jobs()
    assert len(jobs) >= 1
    job_ids = [j["id"] for j in jobs]
    assert "daily_analytical_pipeline" in job_ids

    stopped = stop_scheduler(wait=False)
    assert stopped is True
    assert not is_scheduler_running()


def test_duplicate_scheduler_prevention():
    """Verify multiple start calls do not create duplicate schedulers or jobs."""
    stop_scheduler(wait=False)

    start_scheduler(hour=2, minute=0, enable_flag=True)
    assert is_scheduler_running()

    # Second call should safely succeed and avoid duplicating jobs
    second_start = start_scheduler(hour=2, minute=0, enable_flag=True)
    assert second_start is True

    jobs = get_scheduled_jobs()
    daily_jobs = [j for j in jobs if j["id"] == "daily_analytical_pipeline"]
    assert len(daily_jobs) == 1

    stop_scheduler(wait=False)


def test_scheduler_cron_trigger_2am():
    """Verify daily cron trigger is configured for 2:00 AM."""
    stop_scheduler(wait=False)
    start_scheduler(hour=2, minute=0, enable_flag=True)

    scheduler = get_scheduler()
    job = scheduler.get_job("daily_analytical_pipeline")
    assert job is not None
    assert isinstance(job.trigger, CronTrigger)

    # Check hour and minute fields
    fields = {str(field.name): str(field) for field in job.trigger.fields}
    assert fields.get("hour") == "2"
    assert fields.get("minute") == "0"

    stop_scheduler(wait=False)


def test_run_analytical_pipeline_manual_success(db_session):
    """Verify complete manual pipeline execution and task breakdown."""
    report = run_analytical_pipeline(db=db_session)

    assert "run_id" in report
    assert report["status"] == "SUCCESS"
    assert report["tasks_succeeded"] == 5
    assert report["tasks_total"] == 5
    assert report["total_rows_processed"] > 0
    assert report["duration_seconds"] >= 0.0

    task_details = report["task_details"]
    assert task_details["inventory_forecasting_retraining"]["status"] == "SUCCESS"
    assert task_details["customer_rfm_and_segmentation"]["status"] == "SUCCESS"
    assert task_details["recommendation_similarity_matrix"]["status"] == "SUCCESS"
    assert task_details["daily_revenue_analytics"]["status"] == "SUCCESS"
    assert task_details["low_stock_inventory_alerts"]["status"] == "SUCCESS"

    # Verify audit persistence in DB
    audit_row = db_session.query(WorkflowAuditLog).filter_by(run_id=report["run_id"]).first()
    assert audit_row is not None
    assert audit_row.status == "SUCCESS"
    assert audit_row.total_rows_processed == report["total_rows_processed"]


def test_pipeline_task_failure_marks_partial(db_session):
    """Ensure a failed task does NOT silently mark the pipeline as SUCCESS."""
    # Mock task 2 (customer analytics) to raise an error
    with patch("app.services.customer_service.compute_rfm_metrics", side_effect=RuntimeError("Customer DB timeout")):
        report = run_analytical_pipeline(db=db_session)

    assert report["status"] == "PARTIAL"
    assert report["tasks_succeeded"] < report["tasks_total"]
    assert report["task_details"]["customer_rfm_and_segmentation"]["status"] == "FAILED"
    assert "Customer DB timeout" in report["task_details"]["customer_rfm_and_segmentation"]["error"]
    assert report["error_details"] is not None
    assert "Customer DB timeout" in report["error_details"]

    # Verify audit persisted as PARTIAL
    audit_row = db_session.query(WorkflowAuditLog).filter_by(run_id=report["run_id"]).first()
    assert audit_row is not None
    assert audit_row.status == "PARTIAL"


def test_pipeline_all_tasks_failure_marks_failed(db_session):
    """Ensure all failed tasks result in FAILED overall status."""
    with patch("track_inventory.train_and_track_inventory_model", side_effect=RuntimeError("Model error")), \
         patch("app.services.customer_service.compute_rfm_metrics", side_effect=RuntimeError("RFM error")), \
         patch("app.services.recommendation_service._load_interaction_dataframe", side_effect=RuntimeError("Rec error")), \
         patch("app.services.revenue_service.get_total_revenue", side_effect=RuntimeError("Rev error")), \
         patch("app.services.inventory_service.get_low_stock_alerts", side_effect=RuntimeError("Alert error")):
        report = run_analytical_pipeline(db=db_session)

    assert report["status"] == "FAILED"
    assert report["tasks_succeeded"] == 0


def test_get_workflow_audit_logs(db_session):
    """Verify querying recent audit logs from database."""
    # Run twice
    r1 = run_analytical_pipeline(db=db_session)
    r2 = run_analytical_pipeline(db=db_session)

    logs = get_workflow_audit_logs(db=db_session, limit=10)
    assert len(logs) >= 2
    run_ids = [l["run_id"] for l in logs]
    assert r1["run_id"] in run_ids
    assert r2["run_id"] in run_ids


def test_api_pipeline_audit_and_run(client):
    """Verify GET /analytics/pipeline/audit and POST /analytics/pipeline/run."""
    # Trigger run via API
    run_resp = client.post("/analytics/pipeline/run")
    assert run_resp.status_code == 200
    report = run_resp.json()
    assert "run_id" in report
    assert report["status"] in ("SUCCESS", "PARTIAL")

    # Inspect audit list via API
    audit_resp = client.get("/analytics/pipeline/audit?limit=5")
    assert audit_resp.status_code == 200
    audit_list = audit_resp.json()
    assert isinstance(audit_list, list)
    assert len(audit_list) >= 1
    assert any(a["run_id"] == report["run_id"] for a in audit_list)


def test_disable_background_scheduler_env(monkeypatch):
    """Verify DISABLE_BACKGROUND_SCHEDULER=true prevents scheduler startup."""
    from app.scheduler import start_scheduler, is_scheduler_running, stop_scheduler
    stop_scheduler(wait=False)
    monkeypatch.setenv("DISABLE_BACKGROUND_SCHEDULER", "true")
    assert start_scheduler() is False
    assert not is_scheduler_running()


def test_cross_process_lock_acquisition_and_release():
    """Verify OS-level lock acquisition, duplicate blocking, and clean release."""
    import os
    from app.scheduler import acquire_process_lock, release_process_lock, _LOCK_FILE_PATH
    release_process_lock()

    assert acquire_process_lock() is True
    assert os.path.exists(_LOCK_FILE_PATH)
    # Calling in same handle returns True
    assert acquire_process_lock() is True

    assert release_process_lock() is True
    assert not os.path.exists(_LOCK_FILE_PATH)

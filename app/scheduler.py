"""
app/scheduler.py — Modular APScheduler Background Task & Analytical Pipeline Engine.

Responsibilities:
  1. Non-blocking BackgroundScheduler executing background jobs alongside FastAPI.
  2. Prevention of duplicate scheduler instances during FastAPI reloads or multi-worker starts.
  3. Reusable run_analytical_pipeline() orchestrating:
       - Inventory forecasting retraining & MLflow model tracking/registration.
       - Customer RFM metric refresh and K-Means segmentation.
       - Item-based recommendation similarity matrix refresh.
       - Daily revenue analytics refresh (GMV, AOV, MoM growth, vendor benchmarks).
       - Low-stock inventory detection and structured alert logging.
       - Execution auditing to PostgreSQL / database via WorkflowAuditLog.
  4. Scheduled daily execution at 02:00 AM with misfire protection.
  5. Safe manual execution interface for testing and on-demand trigger.
"""

import os
import sys
import uuid
import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("stockpilot.scheduler")

# Singleton scheduler instance and locks
_scheduler: Optional[BackgroundScheduler] = None
_scheduler_lock_flag = False


def get_scheduler() -> BackgroundScheduler:
    """Returns singleton BackgroundScheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(daemon=True)
    return _scheduler


def is_scheduler_running() -> bool:
    """Checks whether the background scheduler is currently active."""
    global _scheduler
    return _scheduler is not None and _scheduler.running


def run_analytical_pipeline(db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Executes the comprehensive StockPilot analytical pipeline:
      Task 1: Inventory forecasting model retraining & MLflow registration
      Task 2: Customer RFM metric refresh and segmentation
      Task 3: Recommendation similarity matrix refresh
      Task 4: Daily revenue analytics refresh
      Task 5: Low-stock inventory detection and alert generation
      Task 6: Workflow execution auditing and persistence

    Returns structured summary report.
    Never silently marks pipeline as SUCCESS if any task encounters an error.
    """
    from app.models.workflow_audit import WorkflowAuditLog
    from app.models.product import Product
    from app.models.customer import Customer
    from app.services import customer_service, recommendation_service, revenue_service, inventory_service

    run_id = f"pipeline-{uuid.uuid4().hex[:10]}"
    start_time = datetime.utcnow()
    t0 = time.time()
    logger.info(f"▶ Starting analytical pipeline execution [Run ID: {run_id}] at {start_time.isoformat()}")

    close_db_session = False
    if db is None:
        from app.database import SessionLocal
        db = SessionLocal()
        close_db_session = True

    task_details: Dict[str, Dict[str, Any]] = {
        "inventory_forecasting_retraining": {
            "status": "PENDING",
            "duration_seconds": 0.0,
            "rows_processed": 0,
            "error": None,
            "details": {},
        },
        "customer_rfm_and_segmentation": {
            "status": "PENDING",
            "duration_seconds": 0.0,
            "rows_processed": 0,
            "error": None,
            "details": {},
        },
        "recommendation_similarity_matrix": {
            "status": "PENDING",
            "duration_seconds": 0.0,
            "rows_processed": 0,
            "error": None,
            "details": {},
        },
        "daily_revenue_analytics": {
            "status": "PENDING",
            "duration_seconds": 0.0,
            "rows_processed": 0,
            "error": None,
            "details": {},
        },
        "low_stock_inventory_alerts": {
            "status": "PENDING",
            "duration_seconds": 0.0,
            "rows_processed": 0,
            "error": None,
            "details": {},
        },
    }

    error_messages: List[str] = []

    try:
        # ── Task 1: Inventory Forecasting Model Retraining & MLflow Tracking ──
        task_t0 = time.time()
        try:
            logger.info("Executing Task 1: Inventory forecasting model retraining and MLflow tracking...")
            from track_inventory import train_and_track_inventory_model
            mlflow_res = train_and_track_inventory_model(db=db, register=True)
            task_details["inventory_forecasting_retraining"] = {
                "status": "SUCCESS",
                "duration_seconds": round(time.time() - task_t0, 3),
                "rows_processed": mlflow_res.get("rows_processed", 0),
                "error": None,
                "details": {
                    "mlflow_run_id": mlflow_res.get("run_id"),
                    "registered_model": mlflow_res.get("model_name"),
                    "registered_version": mlflow_res.get("model_version"),
                    "metrics": mlflow_res.get("metrics"),
                },
            }
        except Exception as e:
            err = f"Task 1 (inventory forecasting) failed: {str(e)}"
            logger.error(err, exc_info=True)
            error_messages.append(err)
            task_details["inventory_forecasting_retraining"] = {
                "status": "FAILED",
                "duration_seconds": round(time.time() - task_t0, 3),
                "rows_processed": 0,
                "error": str(e),
                "details": {},
            }

        # ── Task 2: Customer RFM Metric Refresh and Segmentation ───────────────
        task_t0 = time.time()
        try:
            logger.info("Executing Task 2: Customer RFM and segmentation refresh...")
            rfm = customer_service.compute_rfm_metrics(db)
            seg = customer_service.segment_customers(db)
            task_details["customer_rfm_and_segmentation"] = {
                "status": "SUCCESS",
                "duration_seconds": round(time.time() - task_t0, 3),
                "rows_processed": len(rfm),
                "error": None,
                "details": {
                    "total_customers": len(rfm),
                    "clusters": seg.get("n_clusters", 0),
                    "silhouette_score": seg.get("silhouette_score", 0.0),
                },
            }
        except Exception as e:
            err = f"Task 2 (customer analytics) failed: {str(e)}"
            logger.error(err, exc_info=True)
            error_messages.append(err)
            task_details["customer_rfm_and_segmentation"] = {
                "status": "FAILED",
                "duration_seconds": round(time.time() - task_t0, 3),
                "rows_processed": 0,
                "error": str(e),
                "details": {},
            }

        # ── Task 3: Recommendation Similarity Matrix Refresh ──────────────────
        task_t0 = time.time()
        try:
            logger.info("Executing Task 3: Recommendation similarity matrix refresh...")
            interaction_df = recommendation_service._load_interaction_dataframe(db)
            item_sim, user_profiles = recommendation_service.build_item_similarity_matrix(interaction_df)
            task_details["recommendation_similarity_matrix"] = {
                "status": "SUCCESS",
                "duration_seconds": round(time.time() - task_t0, 3),
                "rows_processed": len(interaction_df),
                "error": None,
                "details": {
                    "interaction_records": len(interaction_df),
                    "items_in_similarity_matrix": len(item_sim),
                    "user_profiles_mapped": len(user_profiles),
                },
            }
        except Exception as e:
            err = f"Task 3 (recommendations) failed: {str(e)}"
            logger.error(err, exc_info=True)
            error_messages.append(err)
            task_details["recommendation_similarity_matrix"] = {
                "status": "FAILED",
                "duration_seconds": round(time.time() - task_t0, 3),
                "rows_processed": 0,
                "error": str(e),
                "details": {},
            }

        # ── Task 4: Daily Revenue Analytics Refresh ────────────────────────────
        task_t0 = time.time()
        try:
            logger.info("Executing Task 4: Daily revenue analytics refresh...")
            tot_rev = revenue_service.get_total_revenue(db)
            growth = revenue_service.get_monthly_revenue_growth(db)
            bench = revenue_service.get_vendor_benchmarking(db)
            task_details["daily_revenue_analytics"] = {
                "status": "SUCCESS",
                "duration_seconds": round(time.time() - task_t0, 3),
                "rows_processed": growth.get("total_orders", 0),
                "error": None,
                "details": {
                    "total_revenue": tot_rev.get("total_revenue", 0.0),
                    "gmv": growth.get("gmv", 0.0),
                    "aov": growth.get("avg_order_value", 0.0),
                    "vendors_benchmarked": bench.get("vendor_count", 0),
                },
            }
        except Exception as e:
            err = f"Task 4 (revenue analytics) failed: {str(e)}"
            logger.error(err, exc_info=True)
            error_messages.append(err)
            task_details["daily_revenue_analytics"] = {
                "status": "FAILED",
                "duration_seconds": round(time.time() - task_t0, 3),
                "rows_processed": 0,
                "error": str(e),
                "details": {},
            }

        # ── Task 5: Low-Stock Inventory Detection and Alert Generation ─────────
        task_t0 = time.time()
        try:
            logger.info("Executing Task 5: Low-stock inventory detection...")
            alerts = inventory_service.get_low_stock_alerts(db)
            total_items = db.query(Product).count()

            # Structured non-intrusive logging of alerts
            if alerts:
                logger.warning(f"Low-stock alert generated for {len(alerts)} item(s):")
                for a in alerts:
                    logger.warning(
                        f"  [ALERT-{a['severity']}] Product: {a['product_name']} "
                        f"(Stock: {a['current_stock']}, Reorder Level: {a['reorder_level']}, "
                        f"Action: {a['recommended_action']})"
                    )
            else:
                logger.info("Inventory check passed: No low-stock items detected.")

            task_details["low_stock_inventory_alerts"] = {
                "status": "SUCCESS",
                "duration_seconds": round(time.time() - task_t0, 3),
                "rows_processed": total_items,
                "error": None,
                "details": {
                    "products_evaluated": total_items,
                    "alerts_count": len(alerts),
                    "critical_count": sum(1 for a in alerts if a.get("severity") == "CRITICAL"),
                },
            }
        except Exception as e:
            err = f"Task 5 (inventory alerts) failed: {str(e)}"
            logger.error(err, exc_info=True)
            error_messages.append(err)
            task_details["low_stock_inventory_alerts"] = {
                "status": "FAILED",
                "duration_seconds": round(time.time() - task_t0, 3),
                "rows_processed": 0,
                "error": str(e),
                "details": {},
            }

    finally:
        # Determine overall pipeline status: SUCCESS, PARTIAL, or FAILED
        statuses = [t["status"] for t in task_details.values()]
        success_count = statuses.count("SUCCESS")
        total_tasks = len(statuses)

        if success_count == total_tasks:
            overall_status = "SUCCESS"
        elif success_count == 0:
            overall_status = "FAILED"
        else:
            overall_status = "PARTIAL"

        end_time = datetime.utcnow()
        duration_sec = round(time.time() - t0, 3)
        total_rows = sum(t["rows_processed"] for t in task_details.values())

        # ── Task 6: Audit Record Persistence ──────────────────────────────────
        try:
            from app.database import engine, Base
            # Ensure audit table exists
            Base.metadata.create_all(bind=engine)

            audit_log = WorkflowAuditLog(
                run_id=run_id,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration_sec,
                status=overall_status,
                total_rows_processed=total_rows,
                task_details=task_details,
                error_details="; ".join(error_messages) if error_messages else None,
            )
            db.add(audit_log)
            db.commit()
            db.refresh(audit_log)
            logger.info(f"✔ Pipeline audit log persisted: ID={audit_log.id}, Run={run_id}, Status={overall_status}")
        except Exception as e:
            logger.error(f"Failed to persist pipeline audit record: {e}", exc_info=True)
            if db:
                db.rollback()

        if close_db_session and db:
            db.close()

    report = {
        "run_id": run_id,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_seconds": duration_sec,
        "status": overall_status,
        "total_rows_processed": total_rows,
        "tasks_succeeded": success_count,
        "tasks_total": total_tasks,
        "task_details": task_details,
        "error_details": "; ".join(error_messages) if error_messages else None,
    }

    logger.info(
        f"🏁 Analytical pipeline completed [Run ID: {run_id}] in {duration_sec}s with status: {overall_status} "
        f"({success_count}/{total_tasks} tasks succeeded, {total_rows} total rows processed)"
    )
    return report


def start_scheduler(
    hour: int = 2,
    minute: int = 0,
    enable_flag: Optional[bool] = None,
) -> bool:
    """
    Initializes and starts the APScheduler background instance with duplicate prevention.
    Schedules daily analytical pipeline execution at the specified hour:minute (default 2:00 AM).
    """
    global _scheduler_lock_flag
    scheduler = get_scheduler()

    # Determine whether scheduler is enabled
    if enable_flag is None:
        enable_str = os.getenv("ENABLE_SCHEDULER", "true").lower()
        enable_flag = enable_str in ("1", "true", "yes")

    if not enable_flag:
        logger.info("APScheduler is disabled via configuration (ENABLE_SCHEDULER=false).")
        return False

    # Prevent duplicate runs when uvicorn reloads or spawns multiple workers
    if scheduler.running or _scheduler_lock_flag:
        logger.info("APScheduler instance is already running; skipping redundant start.")
        return True

    # Avoid starting redundant scheduler inside uvicorn reloader parent process
    # When uvicorn reloads, RUN_MAIN or UVICORN_RELOAD is set in subprocess
    if os.getenv("WERKZEUG_RUN_MAIN") == "false":
        logger.info("Skipping scheduler startup in parent reloader process.")
        return False

    try:
        # Schedule daily 2:00 AM analytical pipeline
        scheduler.add_job(
            run_analytical_pipeline,
            trigger=CronTrigger(hour=hour, minute=minute),
            id="daily_analytical_pipeline",
            name="Daily Retail Analytics & Model Retraining Pipeline",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        scheduler.start()
        _scheduler_lock_flag = True
        logger.info(
            f"🚀 APScheduler started successfully. Daily pipeline scheduled at {hour:02d}:{minute:02d} AM."
        )
        return True
    except Exception as e:
        logger.error(f"Failed to start APScheduler: {e}", exc_info=True)
        return False


def stop_scheduler(wait: bool = False) -> bool:
    """Safely shuts down the background scheduler."""
    global _scheduler, _scheduler_lock_flag
    if _scheduler is not None and _scheduler.running:
        try:
            _scheduler.shutdown(wait=wait)
            _scheduler_lock_flag = False
            logger.info("APScheduler stopped successfully.")
            return True
        except Exception as e:
            logger.error(f"Error while stopping APScheduler: {e}", exc_info=True)
            return False
    _scheduler_lock_flag = False
    return True


def get_scheduled_jobs() -> List[Dict[str, Any]]:
    """Returns list of active scheduled jobs and next trigger times."""
    scheduler = get_scheduler()
    if not scheduler.running:
        return []
    jobs = []
    for j in scheduler.get_jobs():
        jobs.append({
            "id": j.id,
            "name": j.name,
            "next_run_time": j.next_run_time.isoformat() if j.next_run_time else None,
            "trigger": str(j.trigger),
        })
    return jobs


def get_workflow_audit_logs(db: Session, limit: int = 10) -> List[Dict[str, Any]]:
    """Fetches recent workflow audit execution records from the database."""
    from app.models.workflow_audit import WorkflowAuditLog

    records = (
        db.query(WorkflowAuditLog)
        .order_by(WorkflowAuditLog.start_time.desc())
        .limit(limit)
        .all()
    )
    return [r.to_dict() for r in records]

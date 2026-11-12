"""
models/workflow_audit.py — SQLAlchemy model for Automated Workflow Pipeline Audit Logs.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Text
from app.database import Base


class WorkflowAuditLog(Base):
    """
    Persistent audit record for analytical workflow pipeline executions.
    Tracks run ID, timing, overall status, individual task breakdown,
    rows processed, and error diagnostics.
    """
    __tablename__ = "workflow_audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    run_id = Column(String(64), unique=True, index=True, nullable=False)
    start_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="RUNNING")  # SUCCESS, PARTIAL, FAILED, RUNNING
    total_rows_processed = Column(Integer, default=0, nullable=False)
    task_details = Column(JSON, nullable=True)
    error_details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "status": self.status,
            "total_rows_processed": self.total_rows_processed,
            "task_details": self.task_details or {},
            "error_details": self.error_details,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

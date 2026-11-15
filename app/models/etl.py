"""
models/etl.py — ORM models for ETL ingestion, staging, quarantine, and dimensional data warehouse.

Includes:
  - ETLBatch: Ingestion batch lifecycle and audit summary.
  - ETLStagingRecord: Raw ingestion buffer separating incoming payloads from production data.
  - ETLQuarantineRecord: Isolated invalid records requiring resolution or reprocessing.
  - DailySalesMart: Dimensional data warehouse aggregate mart at (date, product_id, vendor_id) grain.
"""

from datetime import datetime, date
from sqlalchemy import (
    Integer,
    Float,
    String,
    Date,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ETLBatch(Base):
    __tablename__ = "etl_batches"

    batch_id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, default="CSV_INGEST")
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="RECEIVED")
    # Statuses: RECEIVED, PROCESSING, COMPLETED, PARTIALLY_COMPLETED, FAILED

    total_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    staged_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    committed_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quarantined_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    total_gross_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    processing_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    staging_records: Mapped[list["ETLStagingRecord"]] = relationship(
        "ETLStagingRecord", back_populates="batch", cascade="all, delete-orphan"
    )
    quarantine_records: Mapped[list["ETLQuarantineRecord"]] = relationship(
        "ETLQuarantineRecord", back_populates="batch", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "source_system": self.source_system,
            "original_filename": self.original_filename,
            "file_size_bytes": self.file_size_bytes,
            "file_hash": self.file_hash,
            "status": self.status,
            "total_records": self.total_records,
            "staged_records": self.staged_records,
            "committed_records": self.committed_records,
            "duplicate_records": self.duplicate_records,
            "quarantined_records": self.quarantined_records,
            "failed_records": self.failed_records,
            "total_gross_value": self.total_gross_value,
            "processing_duration_ms": self.processing_duration_ms,
            "error_summary": self.error_summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class ETLStagingRecord(Base):
    __tablename__ = "etl_staging_records"

    staging_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("etl_batches.batch_id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_transaction_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    raw_payload: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="STAGED")
    # Statuses: STAGED, VALIDATED, COMMITTED, QUARANTINED, DUPLICATE, FAILED

    validation_errors: Mapped[str | None] = mapped_column(String, nullable=True)
    target_transaction_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("transactions.transaction_id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    batch: Mapped["ETLBatch"] = relationship("ETLBatch", back_populates="staging_records")
    target_transaction: Mapped["Transaction | None"] = relationship("Transaction")  # noqa: F821

    def to_dict(self) -> dict:
        return {
            "staging_id": self.staging_id,
            "batch_id": self.batch_id,
            "row_number": self.row_number,
            "source_transaction_id": self.source_transaction_id,
            "raw_payload": self.raw_payload,
            "status": self.status,
            "validation_errors": self.validation_errors,
            "target_transaction_id": self.target_transaction_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ETLQuarantineRecord(Base):
    __tablename__ = "etl_quarantine_records"

    quarantine_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    staging_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("etl_staging_records.staging_id", ondelete="CASCADE"), nullable=True, index=True
    )
    batch_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("etl_batches.batch_id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_transaction_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    error_category: Mapped[str] = mapped_column(String(50), nullable=False)
    # Categories: VALIDATION_ERROR, MISSING_FOREIGN_KEY, INVALID_DATA_TYPE, MALFORMED_ROW, DUPLICATE_SOURCE_ID
    error_details: Mapped[str] = mapped_column(String, nullable=False)
    raw_data: Mapped[str] = mapped_column(String, nullable=False)
    resolution_status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    # Statuses: PENDING, RESOLVED, IGNORED

    reprocessing_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_reprocessed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    batch: Mapped["ETLBatch"] = relationship("ETLBatch", back_populates="quarantine_records")
    staging_record: Mapped["ETLStagingRecord | None"] = relationship("ETLStagingRecord")

    def to_dict(self) -> dict:
        return {
            "quarantine_id": self.quarantine_id,
            "staging_id": self.staging_id,
            "batch_id": self.batch_id,
            "row_number": self.row_number,
            "source_transaction_id": self.source_transaction_id,
            "error_category": self.error_category,
            "error_details": self.error_details,
            "raw_data": self.raw_data,
            "resolution_status": self.resolution_status,
            "reprocessing_attempts": self.reprocessing_attempts,
            "last_reprocessed_at": self.last_reprocessed_at.isoformat() if self.last_reprocessed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DailySalesMart(Base):
    __tablename__ = "daily_sales_mart"

    __table_args__ = (
        UniqueConstraint("date", "product_id", "vendor_id", name="uq_daily_sales_mart_date_product_vendor"),
        CheckConstraint("units_sold >= 0", name="ck_daily_mart_units_non_negative"),
        CheckConstraint("transaction_count >= 0", name="ck_daily_mart_tx_count_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    units_sold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gross_sales_gmv: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    discounts_total: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    refunds_total: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    net_sales: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Nullable COGS accounting (preserves Stage 4 invariants)
    known_cogs: Mapped[float | None] = mapped_column(Float, nullable=True)
    reported_gross_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    cogs_coverage_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    transaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_refreshed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    product: Mapped["Product"] = relationship("Product")  # noqa: F821
    vendor: Mapped["Vendor"] = relationship("Vendor")  # noqa: F821

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.date.isoformat() if self.date else None,
            "product_id": self.product_id,
            "vendor_id": self.vendor_id,
            "category": self.category,
            "units_sold": self.units_sold,
            "gross_sales_gmv": round(self.gross_sales_gmv, 2),
            "discounts_total": round(self.discounts_total, 2),
            "refunds_total": round(self.refunds_total, 2),
            "net_sales": round(self.net_sales, 2),
            "known_cogs": round(self.known_cogs, 2) if self.known_cogs is not None else None,
            "reported_gross_profit": round(self.reported_gross_profit, 2) if self.reported_gross_profit is not None else None,
            "cogs_coverage_pct": round(self.cogs_coverage_pct, 2),
            "transaction_count": self.transaction_count,
            "last_refreshed_at": self.last_refreshed_at.isoformat() if self.last_refreshed_at else None,
        }

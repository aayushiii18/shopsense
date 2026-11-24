"""
schemas/etl_schema.py — Pydantic models for ETL batches, staging, quarantine, reconciliation, and data warehouse.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class ETLBatchResponse(BaseModel):
    batch_id: str
    source_system: str
    original_filename: str
    file_size_bytes: Optional[int] = None
    file_hash: Optional[str] = None
    status: str
    total_records: int
    staged_records: int
    committed_records: int
    duplicate_records: int
    quarantined_records: int
    failed_records: int
    total_gross_value: float
    processing_duration_ms: Optional[float] = None
    error_summary: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ETLBatchListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    batches: List[ETLBatchResponse]


class ETLStagingRecordResponse(BaseModel):
    staging_id: int
    batch_id: str
    row_number: int
    source_transaction_id: Optional[str] = None
    raw_payload: str
    status: str
    validation_errors: Optional[str] = None
    target_transaction_id: Optional[int] = None
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ETLStagingListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    records: List[ETLStagingRecordResponse]


class ETLQuarantineRecordResponse(BaseModel):
    quarantine_id: int
    staging_id: Optional[int] = None
    batch_id: str
    row_number: int
    source_transaction_id: Optional[str] = None
    error_category: str
    error_details: str
    raw_data: str
    resolution_status: str
    reprocessing_attempts: int
    last_reprocessed_at: Optional[str] = None
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ETLQuarantineListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    records: List[ETLQuarantineRecordResponse]


class QuarantineReprocessRequest(BaseModel):
    corrected_data: Optional[Dict[str, Any]] = None


class DailySalesMartRecordResponse(BaseModel):
    id: int
    date: str
    product_id: int
    vendor_id: int
    category: str
    units_sold: int
    gross_sales_gmv: float
    discounts_total: float
    refunds_total: float
    net_sales: float
    known_cogs: Optional[float] = None
    reported_gross_profit: Optional[float] = None
    cogs_coverage_pct: float
    transaction_count: int
    last_refreshed_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DailySalesMartQueryResponse(BaseModel):
    total: int
    limit: int
    offset: int
    summary: Dict[str, Any]
    records: List[DailySalesMartRecordResponse]


class DailySalesMartRefreshRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    full_rebuild: bool = False

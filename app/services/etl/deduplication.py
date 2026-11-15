"""
services/etl/deduplication.py — Deduplication and idempotency engine for external retail transactions.

Enforces:
  - Database-backed idempotency on (source_system, source_transaction_id).
  - In-batch deduplication: flags subsequent identical source IDs within the same file.
  - Cross-batch deduplication: detects previously committed transactions in production.
  - Transparent audit tracking of duplicate counts and rationale.
"""

from typing import List, Dict, Any, Set, Tuple, Optional
from sqlalchemy.orm import Session
from app.models.transaction import Transaction


class DeduplicationResult:
    def __init__(
        self,
        unique_records: List[Dict[str, Any]],
        duplicate_records: List[Dict[str, Any]],
        in_batch_duplicates_count: int,
        cross_batch_duplicates_count: int,
    ):
        self.unique_records = unique_records
        self.duplicate_records = duplicate_records
        self.in_batch_duplicates_count = in_batch_duplicates_count
        self.cross_batch_duplicates_count = cross_batch_duplicates_count

    @property
    def total_duplicates(self) -> int:
        return self.in_batch_duplicates_count + self.cross_batch_duplicates_count


def deduplicate_chunk(
    db: Session,
    records: List[Dict[str, Any]],
    source_system: str,
    seen_in_batch: Set[str],
) -> DeduplicationResult:
    """
    Deduplicates a chunk of validated records against:
      1. seen_in_batch set (in-file duplication)
      2. existing database transactions with (source_system, source_transaction_id) (cross-batch duplication)
    """
    unique_list: List[Dict[str, Any]] = []
    duplicate_list: List[Dict[str, Any]] = []
    in_batch_count = 0
    cross_batch_count = 0

    # Collect source_transaction_ids from this chunk that have an external ID
    chunk_source_ids = [
        str(r["source_transaction_id"])
        for r in records
        if r.get("source_transaction_id") is not None and str(r.get("source_transaction_id")).strip() != ""
    ]

    # Pre-fetch existing database source_ids in one single query to eliminate N+1 overhead
    existing_db_ids: Set[str] = set()
    if chunk_source_ids:
        rows = (
            db.query(Transaction.source_transaction_id)
            .filter(
                Transaction.source_system == source_system,
                Transaction.source_transaction_id.in_(chunk_source_ids),
            )
            .all()
        )
        existing_db_ids = {r[0] for r in rows if r[0] is not None}

    for rec in records:
        src_id = rec.get("source_transaction_id")
        if src_id is None or str(src_id).strip() == "":
            # Records without external source ID cannot conflict on idempotency key
            unique_list.append(rec)
            continue

        src_id_str = str(src_id).strip()

        # Check in-batch collision
        if src_id_str in seen_in_batch:
            in_batch_count += 1
            duplicate_list.append({
                "record": rec,
                "reason": f"Duplicate source_transaction_id '{src_id_str}' within the same batch upload (in-batch collision)",
                "type": "IN_BATCH_DUPLICATE",
            })
            continue

        # Check cross-batch database collision
        if src_id_str in existing_db_ids:
            cross_batch_count += 1
            duplicate_list.append({
                "record": rec,
                "reason": f"Transaction with source_system '{source_system}' and source_transaction_id '{src_id_str}' already exists in database (cross-batch collision)",
                "type": "CROSS_BATCH_DUPLICATE",
            })
            continue

        # Unseen and not in DB
        seen_in_batch.add(src_id_str)
        unique_list.append(rec)

    return DeduplicationResult(
        unique_records=unique_list,
        duplicate_records=duplicate_list,
        in_batch_duplicates_count=in_batch_count,
        cross_batch_duplicates_count=cross_batch_count,
    )

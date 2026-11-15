"""
services/etl/extract.py — CSV extraction, chunking, encoding detection, and header validation.

Provides:
  - extract_chunks: Streaming generator reading large CSVs in bounded chunks.
  - detect_encoding_and_delimiter: Sniffing encoding and dialect delimiters safely.
  - validate_and_map_headers: Validates required column headers and applies aliases.
  - compute_file_hash: Computes SHA-256 hash for batch idempotency / file tracking.
"""

import io
import csv
import hashlib
from typing import BinaryIO, Generator, List, Dict, Any, Tuple, Optional


DEFAULT_REQUIRED_COLUMNS = ["product_id", "vendor_id", "quantity", "unit_price"]

COLUMN_ALIASES: Dict[str, str] = {
    "source_transaction_id": "source_transaction_id",
    "transaction_id": "source_transaction_id",
    "source_tx_id": "source_transaction_id",
    "order_id": "source_transaction_id",
    "id": "source_transaction_id",
    "product_id": "product_id",
    "product": "product_id",
    "vendor_id": "vendor_id",
    "vendor": "vendor_id",
    "customer_id": "customer_id",
    "customer": "customer_id",
    "quantity": "quantity",
    "qty": "quantity",
    "unit_price": "unit_price",
    "price": "unit_price",
    "item_price": "unit_price",
    "amount": "amount",
    "total_amount": "amount",
    "total_price": "amount",
    "discount_amount": "discount_amount",
    "discount": "discount_amount",
    "payment_method": "payment_method",
    "payment_status": "payment_status",
    "transaction_date": "transaction_date",
    "date": "transaction_date",
    "created_at": "transaction_date",
}


def compute_file_hash(data: bytes) -> str:
    """Computes SHA-256 hash of raw file bytes."""
    return hashlib.sha256(data).hexdigest()


def detect_encoding_and_delimiter(sample_bytes: bytes) -> Tuple[str, str]:
    """
    Attempts common UTF-8 / Latin-1 encodings and sniffs CSV delimiter.
    Defaults to utf-8 and comma on ambiguity.
    """
    encodings_to_try = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
    decoded_text = None
    chosen_encoding = "utf-8"

    for enc in encodings_to_try:
        try:
            decoded_text = sample_bytes.decode(enc)
            chosen_encoding = enc
            break
        except UnicodeDecodeError:
            continue

    if decoded_text is None:
        decoded_text = sample_bytes.decode("utf-8", errors="replace")
        chosen_encoding = "utf-8"

    # Sniff delimiter from first few lines
    sample_snippet = "\n".join(decoded_text.splitlines()[:5])
    try:
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(sample_snippet, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except Exception:
        delimiter = ","

    return chosen_encoding, delimiter


def normalize_headers(
    headers: List[str], custom_mapping: Optional[Dict[str, str]] = None
) -> Tuple[Dict[str, str], List[str]]:
    """
    Maps incoming raw header names to canonical schema keys.
    Returns (mapping_dict: canonical -> raw, missing_required_fields: list).
    """
    canonical_map: Dict[str, str] = {}
    normalized_incoming = {h.strip().lower().replace(" ", "_"): h for h in headers if h}

    # Apply user-supplied custom mapping first
    if custom_mapping:
        for user_key, canonical_target in custom_mapping.items():
            norm_k = user_key.strip().lower().replace(" ", "_")
            if norm_k in normalized_incoming:
                canonical_map[canonical_target] = normalized_incoming[norm_k]

    # Fill remaining from built-in alias dictionary
    for alias_raw, canonical_target in COLUMN_ALIASES.items():
        if canonical_target not in canonical_map and alias_raw in normalized_incoming:
            canonical_map[canonical_target] = normalized_incoming[alias_raw]

    missing = [req for req in DEFAULT_REQUIRED_COLUMNS if req not in canonical_map]
    return canonical_map, missing


def extract_chunks(
    file_stream: BinaryIO,
    chunk_size: int = 1000,
    custom_mapping: Optional[Dict[str, str]] = None,
) -> Generator[Tuple[int, List[Dict[str, Any]], Dict[str, str]], None, None]:
    """
    Streams CSV content in chunks of `chunk_size` rows.
    Yields: (chunk_index, rows_list, canonical_header_mapping)
    Each row in rows_list is a dict with keys:
      - "_row_number": 1-based original file line number
      - "_raw_payload": original raw dictionary as extracted
      - Canonical keys mapped from columns (e.g. "product_id", "vendor_id", etc.)
    """
    file_stream.seek(0)
    sample_bytes = file_stream.read(8192)
    file_stream.seek(0)

    encoding, delimiter = detect_encoding_and_delimiter(sample_bytes)

    # Read entire stream safely decoded
    text_stream = io.TextIOWrapper(file_stream, encoding=encoding, newline="")
    reader = csv.DictReader(text_stream, delimiter=delimiter)

    if not reader.fieldnames:
        return

    raw_headers = [h.strip() for h in reader.fieldnames if h]
    canonical_map, missing = normalize_headers(raw_headers, custom_mapping)

    chunk: List[Dict[str, Any]] = []
    chunk_idx = 0
    row_num = 1  # header is line 1, first record is line 2

    for raw_row in reader:
        row_num += 1
        cleaned_row: Dict[str, Any] = {
            "_row_number": row_num,
            "_raw_payload": {k: v for k, v in raw_row.items() if k is not None},
        }

        # Map canonical fields
        for canonical_name, raw_name in canonical_map.items():
            val = raw_row.get(raw_name)
            if val is not None:
                cleaned_row[canonical_name] = val.strip() if isinstance(val, str) else val
            else:
                cleaned_row[canonical_name] = None

        chunk.append(cleaned_row)

        if len(chunk) >= chunk_size:
            yield chunk_idx, chunk, canonical_map
            chunk_idx += 1
            chunk = []

    if chunk:
        yield chunk_idx, chunk, canonical_map

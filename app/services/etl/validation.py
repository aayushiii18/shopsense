"""
services/etl/validation.py — Row-level schema validation, range checks, and referential integrity.

Validates:
  - Presence of required fields: product_id, vendor_id, quantity, unit_price.
  - Type conversions: integer IDs, integer quantity, float prices.
  - Numeric ranges: quantity > 0, unit_price > 0, discount_amount >= 0, amount > 0.
  - Foreign key existence against active database catalog (cached sets).
  - Timestamp parsing across diverse date formats.
  - Categorization of errors into VALIDATION_ERROR, INVALID_DATA_TYPE, MISSING_FOREIGN_KEY, MALFORMED_ROW.
"""

from datetime import datetime
from typing import Dict, Any, List, Set, Optional, Tuple


class ValidationResult:
    def __init__(
        self,
        is_valid: bool,
        row_number: int,
        cleaned_record: Optional[Dict[str, Any]] = None,
        errors: Optional[List[str]] = None,
        error_category: Optional[str] = None,
    ):
        self.is_valid = is_valid
        self.row_number = row_number
        self.cleaned_record = cleaned_record or {}
        self.errors = errors or []
        self.error_category = error_category or "VALIDATION_ERROR"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "row_number": self.row_number,
            "errors": self.errors,
            "error_category": self.error_category,
            "cleaned_record": self.cleaned_record,
        }


def parse_datetime_flexible(val: Any) -> Optional[datetime]:
    """Parses various date/time formats commonly found in retail exports."""
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val

    s = str(val).strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s)
    except Exception:
        pass
    return None


def validate_row(
    row: Dict[str, Any],
    valid_product_ids: Set[int],
    valid_vendor_ids: Set[int],
    valid_customer_ids: Set[int],
    product_vendor_map: Optional[Dict[int, int]] = None,
) -> ValidationResult:
    """
    Validates a single staged row against retail schema rules and database foreign keys.
    """
    row_num = row.get("_row_number", 0)
    errors: List[str] = []
    error_category = "VALIDATION_ERROR"

    cleaned: Dict[str, Any] = {
        "_row_number": row_num,
        "source_transaction_id": row.get("source_transaction_id"),
        "payment_method": row.get("payment_method") or "UNKNOWN",
        "payment_status": row.get("payment_status") or "COMPLETED",
    }

    # 1. Product ID
    raw_pid = row.get("product_id")
    if raw_pid is None or str(raw_pid).strip() == "":
        errors.append("Missing required field 'product_id'")
    else:
        try:
            pid = int(raw_pid)
            if pid not in valid_product_ids:
                errors.append(f"Referenced product_id {pid} does not exist in product catalog")
                error_category = "MISSING_FOREIGN_KEY"
            else:
                cleaned["product_id"] = pid
        except ValueError:
            errors.append(f"Invalid integer data type for product_id: '{raw_pid}'")
            error_category = "INVALID_DATA_TYPE"

    # 2. Vendor ID
    raw_vid = row.get("vendor_id")
    if raw_vid is None or str(raw_vid).strip() == "":
        errors.append("Missing required field 'vendor_id'")
    else:
        try:
            vid = int(raw_vid)
            if vid not in valid_vendor_ids:
                errors.append(f"Referenced vendor_id {vid} does not exist in vendors registry")
                error_category = "MISSING_FOREIGN_KEY"
            else:
                cleaned["vendor_id"] = vid
        except ValueError:
            errors.append(f"Invalid integer data type for vendor_id: '{raw_vid}'")
            error_category = "INVALID_DATA_TYPE"

    # Optional cross-check: Product belongs to Vendor
    if "product_id" in cleaned and "vendor_id" in cleaned and product_vendor_map:
        expected_vid = product_vendor_map.get(cleaned["product_id"])
        if expected_vid is not None and expected_vid != cleaned["vendor_id"]:
            errors.append(
                f"Product ID {cleaned['product_id']} belongs to vendor {expected_vid}, not vendor {cleaned['vendor_id']}"
            )
            error_category = "MISSING_FOREIGN_KEY"

    # 3. Customer ID (nullable, but must be valid if supplied)
    raw_cid = row.get("customer_id")
    if raw_cid is not None and str(raw_cid).strip() != "":
        try:
            cid = int(raw_cid)
            if cid not in valid_customer_ids:
                errors.append(f"Referenced customer_id {cid} does not exist in customers registry")
                error_category = "MISSING_FOREIGN_KEY"
            else:
                cleaned["customer_id"] = cid
        except ValueError:
            errors.append(f"Invalid integer data type for customer_id: '{raw_cid}'")
            error_category = "INVALID_DATA_TYPE"
    else:
        cleaned["customer_id"] = None

    # 4. Quantity
    raw_qty = row.get("quantity")
    if raw_qty is None or str(raw_qty).strip() == "":
        errors.append("Missing required field 'quantity'")
    else:
        try:
            qty = int(raw_qty)
            if qty <= 0:
                errors.append(f"Quantity must be strictly positive (> 0), got: {qty}")
            else:
                cleaned["quantity"] = qty
        except ValueError:
            errors.append(f"Invalid integer data type for quantity: '{raw_qty}'")
            error_category = "INVALID_DATA_TYPE"

    # 5. Unit Price
    raw_price = row.get("unit_price")
    if raw_price is None or str(raw_price).strip() == "":
        errors.append("Missing required field 'unit_price'")
    else:
        try:
            price = float(raw_price)
            if price <= 0.0:
                errors.append(f"Unit price must be strictly positive (> 0), got: {price}")
            else:
                cleaned["unit_price"] = round(price, 2)
        except ValueError:
            errors.append(f"Invalid numeric data type for unit_price: '{raw_price}'")
            error_category = "INVALID_DATA_TYPE"

    # 6. Discount Amount (optional, non-negative)
    raw_discount = row.get("discount_amount")
    if raw_discount is not None and str(raw_discount).strip() != "":
        try:
            disc = float(raw_discount)
            if disc < 0.0:
                errors.append(f"Discount amount cannot be negative, got: {disc}")
            else:
                cleaned["discount_amount"] = round(disc, 2)
        except ValueError:
            errors.append(f"Invalid numeric data type for discount_amount: '{raw_discount}'")
            error_category = "INVALID_DATA_TYPE"
    else:
        cleaned["discount_amount"] = 0.0

    # 7. Total Amount (computed or verified)
    raw_amount = row.get("amount")
    if "quantity" in cleaned and "unit_price" in cleaned:
        expected_amount = round(cleaned["quantity"] * cleaned["unit_price"], 2)
        if raw_amount is not None and str(raw_amount).strip() != "":
            try:
                amt = float(raw_amount)
                if amt <= 0.0:
                    errors.append(f"Amount must be strictly positive, got: {amt}")
                else:
                    # Respect provided amount or fallback to calculated
                    cleaned["amount"] = round(amt, 2)
            except ValueError:
                errors.append(f"Invalid numeric data type for amount: '{raw_amount}'")
                error_category = "INVALID_DATA_TYPE"
        else:
            cleaned["amount"] = expected_amount

    # 8. Transaction Date
    raw_date = row.get("transaction_date")
    if raw_date is not None and str(raw_date).strip() != "":
        parsed_dt = parse_datetime_flexible(raw_date)
        if parsed_dt is None:
            errors.append(f"Malformed transaction_date: '{raw_date}' could not be parsed")
            error_category = "MALFORMED_ROW"
        else:
            cleaned["transaction_date"] = parsed_dt
    else:
        cleaned["transaction_date"] = datetime.utcnow()

    # Pass/fail decision
    is_valid = len(errors) == 0
    return ValidationResult(
        is_valid=is_valid,
        row_number=row_num,
        cleaned_record=cleaned if is_valid else None,
        errors=errors,
        error_category=error_category if not is_valid else None,
    )

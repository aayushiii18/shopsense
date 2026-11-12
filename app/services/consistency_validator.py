"""
app/services/consistency_validator.py — Automated Dashboard & Database Consistency Engine.

Cross-validates:
  1. Total Revenue vs Direct Transaction Sum.
  2. GMV vs Total Revenue.
  3. Average Order Value (AOV) vs Statistical Mean.
  4. Vendor Revenue Aggregations vs Total GMV.
  5. Vendor Market Share Sum vs 100.0%.
  6. Customer Count vs Registered Database Count.
  7. Customer Spend Metrics vs Analytical Aggregations.
  8. Inventory Catalog Stock Sum vs Physical Stock Records.
  9. Low-Stock Alert Count vs Database Reorder Threshold Violations.
  10. Demand Forecasting Outputs vs Model Output Bounds.
  11. Customer Segmentation Totals vs Active Customer Population.
  12. Days Sales of Inventory (DSI) Formula Invariant (DSI * Turnover = Days).
"""

import math
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.vendor import Vendor
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.transaction import Transaction
from app.models.customer import Customer
from app.services import revenue_service, customer_service, inventory_service

logger = logging.getLogger("consistency_validator")


def run_consistency_validation(db: Session, tolerance_pct: float = 0.5) -> Dict[str, Any]:
    """
    Executes all cross-system data consistency audits between dashboard calculations
    and underlying PostgreSQL / database state.
    """
    checks: List[Dict[str, Any]] = []

    # 1. Total Revenue Consistency
    db_tot_rev = float(db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).scalar() or 0.0)
    service_tot_rev = revenue_service.get_total_revenue(db).get("total_revenue", 0.0)
    rev_diff = abs(db_tot_rev - service_tot_rev)
    rev_passed = rev_diff <= (db_tot_rev * (tolerance_pct / 100.0) + 0.05)
    checks.append({
        "name": "Total Revenue vs DB Transaction Sum",
        "expected": round(db_tot_rev, 2),
        "actual": round(service_tot_rev, 2),
        "diff": round(rev_diff, 2),
        "passed": rev_passed,
        "category": "Revenue Intelligence",
    })

    # 2. GMV Consistency with Monthly Revenue
    growth_info = revenue_service.get_monthly_revenue_growth(db)
    gmv_val = growth_info.get("gmv", 0.0)
    gmv_passed = math.isclose(gmv_val, service_tot_rev, abs_tol=0.05)
    checks.append({
        "name": "GMV vs Total Revenue Equivalence",
        "expected": round(service_tot_rev, 2),
        "actual": round(gmv_val, 2),
        "diff": round(abs(service_tot_rev - gmv_val), 2),
        "passed": gmv_passed,
        "category": "Revenue Intelligence",
    })

    # 3. Average Order Value (AOV) Consistency
    tx_count = db.query(func.count(Transaction.transaction_id)).scalar() or 0
    expected_aov = round(db_tot_rev / tx_count, 2) if tx_count > 0 else 0.0
    actual_aov = growth_info.get("avg_order_value", 0.0)
    aov_passed = math.isclose(expected_aov, actual_aov, abs_tol=0.05)
    checks.append({
        "name": "Average Order Value (AOV) Calculation",
        "expected": expected_aov,
        "actual": actual_aov,
        "diff": round(abs(expected_aov - actual_aov), 2),
        "passed": aov_passed,
        "category": "Revenue Intelligence",
    })

    # 4. Vendor Performance Sum Consistency
    vendor_items = revenue_service.get_vendor_performance(db)
    vendor_sum = round(sum(v.get("amount", 0.0) for v in vendor_items), 2)
    ven_sum_passed = math.isclose(vendor_sum, service_tot_rev, abs_tol=0.10)
    checks.append({
        "name": "Vendor-wise Revenue Sum vs GMV",
        "expected": round(service_tot_rev, 2),
        "actual": vendor_sum,
        "diff": round(abs(service_tot_rev - vendor_sum), 2),
        "passed": ven_sum_passed,
        "category": "Revenue Intelligence",
    })

    # 5. Vendor Market Share Sum to 100%
    bench_info = revenue_service.get_vendor_benchmarking(db)
    benchmarks = bench_info.get("benchmarks", [])
    share_sum = round(sum(b.get("market_share_pct", 0.0) for b in benchmarks), 1)
    expected_share = 100.0 if benchmarks and service_tot_rev > 0 else 0.0
    share_passed = math.isclose(share_sum, expected_share, abs_tol=0.5)
    checks.append({
        "name": "Vendor Market Share Normalization (Sum = 100%)",
        "expected": expected_share,
        "actual": share_sum,
        "diff": round(abs(expected_share - share_sum), 2),
        "passed": share_passed,
        "category": "Revenue Intelligence",
    })

    # 6. Customer Count Consistency
    db_cust_count = db.query(func.count(Customer.customer_id)).scalar() or 0
    cust_summary = customer_service.get_customer_summary(db)
    cust_count_actual = cust_summary.get("total_customers", 0)
    checks.append({
        "name": "Registered Customer Count Consistency",
        "expected": db_cust_count,
        "actual": cust_count_actual,
        "diff": abs(db_cust_count - cust_count_actual),
        "passed": (db_cust_count == cust_count_actual),
        "category": "Customer Intelligence",
    })

    # 7. Customer Average Lifetime Spend Consistency
    expected_cust_spend = round(db_tot_rev / db_cust_count, 2) if db_cust_count > 0 else 0.0
    actual_cust_spend = cust_summary.get("avg_customer_spend", 0.0)
    cust_spend_passed = math.isclose(expected_cust_spend, actual_cust_spend, abs_tol=0.05)
    checks.append({
        "name": "Customer Lifetime Spend Average",
        "expected": expected_cust_spend,
        "actual": actual_cust_spend,
        "diff": round(abs(expected_cust_spend - actual_cust_spend), 2),
        "passed": cust_spend_passed,
        "category": "Customer Intelligence",
    })

    # 8. Inventory Current Stock Sum Consistency
    db_stock_sum = int(db.query(func.coalesce(func.sum(Inventory.current_stock), 0)).scalar() or 0)
    inv_turnover = inventory_service.calculate_inventory_turnover(db)
    actual_stock_sum = inv_turnover.get("catalog_summary", {}).get("total_current_stock", 0)
    checks.append({
        "name": "Catalog Total Physical Stock Quantity",
        "expected": db_stock_sum,
        "actual": actual_stock_sum,
        "diff": abs(db_stock_sum - actual_stock_sum),
        "passed": (db_stock_sum == actual_stock_sum),
        "category": "Inventory Intelligence",
    })

    # 9. Low-Stock Alert Product Count Consistency
    db_low_stock = db.query(Inventory).filter(Inventory.current_stock <= Inventory.reorder_level).count()
    service_alerts = inventory_service.get_low_stock_alerts(db)
    actual_alert_count = len(service_alerts)
    checks.append({
        "name": "Low-Stock Reorder Threshold Violations",
        "expected": db_low_stock,
        "actual": actual_alert_count,
        "diff": abs(db_low_stock - actual_alert_count),
        "passed": (db_low_stock == actual_alert_count),
        "category": "Inventory Intelligence",
    })

    # 10. Inventory Turnover DSI Formula Mathematical Invariant
    cat_summary = inv_turnover.get("catalog_summary", {})
    turnover_ratio = cat_summary.get("catalog_turnover_ratio", 0.0)
    dsi_val = cat_summary.get("catalog_dsi", 0.0)
    days_period = inv_turnover.get("period_days", 365)
    if turnover_ratio > 0:
        invariant_val = round(turnover_ratio * dsi_val, 0)
        dsi_passed = math.isclose(invariant_val, days_period, abs_tol=5.0)
    else:
        dsi_passed = True
        invariant_val = days_period
    checks.append({
        "name": "Inventory DSI x Turnover Mathematical Invariant",
        "expected": days_period,
        "actual": invariant_val,
        "diff": round(abs(days_period - invariant_val), 1),
        "passed": dsi_passed,
        "category": "Inventory Intelligence",
    })

    # 11. Customer RFM Metric Customer Population Completeness
    rfm_list = customer_service.compute_rfm_metrics(db)
    rfm_count = len(rfm_list)
    checks.append({
        "name": "Customer RFM Completeness (All Customers Evaluated)",
        "expected": db_cust_count,
        "actual": rfm_count,
        "diff": abs(db_cust_count - rfm_count),
        "passed": (db_cust_count == rfm_count),
        "category": "Customer Intelligence",
    })

    # 12. Monthly Demand Forecasting Output Consistency
    forecast_6 = inventory_service.predict_monthly_demand(month=6, db=db)
    fc_passed = (
        forecast_6.get("month") == 6
        and forecast_6.get("units_predicted", 0) > 0
        and forecast_6.get("model_name") == "RandomForest"
    )
    checks.append({
        "name": "Inventory Demand Forecast Model Inference Bounds",
        "expected": "Positive integer prediction (RandomForest)",
        "actual": f"{forecast_6.get('units_predicted')} units ({forecast_6.get('model_name')})",
        "diff": 0,
        "passed": fc_passed,
        "category": "Recommendation Intelligence",
    })

    # Summary
    passed_count = sum(1 for c in checks if c["passed"])
    total_checks = len(checks)
    consistency_pct = round((passed_count / total_checks) * 100.0, 2)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "total_checks": total_checks,
        "passed_checks": passed_count,
        "failed_checks": total_checks - passed_count,
        "consistency_pct": consistency_pct,
        "target_pct": 99.0,
        "target_met": (consistency_pct >= 99.0),
        "checks": checks,
    }

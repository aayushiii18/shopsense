"""
services/cohort_service.py — Monthly Cohort Retention Analysis Engine.
Stage 5 Module 3.

Features:
  - Identifies customer cohorts using official signup_date (Jun–Dec 2023).
  - Also provides alternative first-purchase cohort analysis across calendar 2024.
  - Computes period-over-period customer activity and percentage retention across all 12 calendar months of 2024.
  - Formats data matrices for interactive heatmap visualization.
  - Zero data fabrication: strictly reflects actual database transactions.
"""

from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.transaction import Transaction


def compute_cohort_retention(db: Session, cohort_type: str = "signup_month") -> Dict[str, Any]:
    """
    Computes monthly cohort retention matrices.
    Supported cohort types:
      - 'signup_month': Grouped by customer signup month (June 2023 – Dec 2023).
      - 'first_purchase_month': Grouped by customer first transaction month in 2024.
    """
    customers = db.query(Customer).all()
    txns = db.query(Transaction).all()

    if not customers or not txns:
        return {
            "cohort_type": cohort_type,
            "total_cohorts": 0,
            "cohorts": [],
            "average_retention_by_period": {},
            "methodology_note": "Insufficient customer or transaction records.",
        }

    c_df = pd.DataFrame([
        {
            "customer_id": c.customer_id,
            "signup_date": pd.to_datetime(c.signup_date),
            "signup_month": pd.to_datetime(c.signup_date).strftime("%Y-%m"),
        }
        for c in customers
    ])

    t_df = pd.DataFrame([
        {
            "customer_id": t.customer_id,
            "date": pd.to_datetime(t.transaction_date),
            "txn_month": pd.to_datetime(t.transaction_date).strftime("%Y-%m"),
        }
        for t in txns if t.customer_id is not None
    ])

    # Slices for cohorts
    if cohort_type == "first_purchase_month":
        first_tx = t_df.groupby("customer_id")["date"].min().reset_index()
        first_tx["first_month"] = first_tx["date"].dt.strftime("%Y-%m")
        c_df = c_df.merge(first_tx[["customer_id", "first_month"]], on="customer_id", how="left")
        c_df["cohort_key"] = c_df["first_month"].fillna("No Purchase")
    else:
        # Default: signup month
        c_df["cohort_key"] = c_df["signup_month"]

    # Activity months in 2024: 2024-01 to 2024-12
    activity_months = [f"2024-{m:02d}" for m in range(1, 13)]

    cohort_results = []
    period_sums = {i + 1: [] for i in range(len(activity_months))}

    unique_cohorts = sorted([c for c in c_df["cohort_key"].unique() if c != "No Purchase"])

    for cohort_label in unique_cohorts:
        cohort_cids = set(c_df[c_df["cohort_key"] == cohort_label]["customer_id"])
        cohort_size = len(cohort_cids)
        if cohort_size == 0:
            continue

        period_items = []
        for p_idx, act_month in enumerate(activity_months):
            p_num = p_idx + 1

            # Count unique customers in this cohort who purchased in this activity month
            active_in_month = t_df[
                (t_df["customer_id"].isin(cohort_cids)) &
                (t_df["txn_month"] == act_month)
            ]["customer_id"].nunique()

            retention_pct = round((active_in_month / cohort_size * 100.0), 2)
            period_items.append({
                "period_month": p_num,
                "activity_month_label": act_month,
                "active_customers": int(active_in_month),
                "retention_pct": retention_pct,
            })
            period_sums[p_num].append(retention_pct)

        cohort_results.append({
            "cohort_label": cohort_label,
            "cohort_size": cohort_size,
            "retention_periods": period_items,
        })

    # Average retention across cohorts for each period
    avg_by_period = {
        p_num: round(float(np.mean(vals)), 2) if vals else 0.0
        for p_num, vals in period_sums.items()
    }

    return {
        "cohort_type": cohort_type,
        "total_cohorts": len(cohort_results),
        "cohorts": cohort_results,
        "average_retention_by_period": avg_by_period,
        "methodology_note": (
            f"Calculated using empirical calendar activity across 2024. "
            f"Cohort size represents all customers registered in the signup period. "
            f"Retention % represents the proportion of that cohort placing >= 1 order in the given activity month."
        ),
    }

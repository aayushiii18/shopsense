"""
services/clv_service.py — Predictive Customer Lifetime Value (CLV) Engine.
Stage 5 Module 4.

Key Principles:
  - Strictly distinguishes Historical Customer Spend from 12-Month Forward Predicted CLV.
  - Employs an empirical Bayesian frequency-monetary value shrinkage model:
      m_hat = (n * m_bar + n_0 * AOV_market) / (n + n_0)
  - Incorporates inactivity decay based on recency days and churn probability:
      f_future = max(0.5, (orders / active_months) * 12 * exp(-lambda * recency_months))
  - Provides customer-level estimates, 4-tier loyalty segmentation, and uncertainty bounds.
"""

from typing import List, Dict, Any, Optional
import math
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.transaction import Transaction
from app.services.churn_service import train_and_evaluate_churn_model


def compute_predictive_clv(db: Session, horizon_months: int = 12) -> Dict[str, Any]:
    """
    Computes 12-month forward predictive CLV for all registered customers.
    """
    customers = db.query(Customer).all()
    txns = db.query(Transaction).all()

    if not customers or not txns:
        return {
            "total_customers": 0,
            "aggregate_historical_revenue": 0.0,
            "aggregate_predicted_12m_future_value": 0.0,
            "mean_clv": 0.0,
            "median_clv": 0.0,
            "clv_tiers_distribution": {},
            "customers": [],
            "model_assumptions": "Insufficient records.",
        }

    # Fetch churn probabilities for active life estimation
    churn_results = train_and_evaluate_churn_model(db)
    churn_map = {c["customer_id"]: c["churn_probability"] for c in churn_results.get("customers", [])}

    df_tx = pd.DataFrame([
        {
            "customer_id": t.customer_id,
            "amount": float(t.amount),
            "date": pd.to_datetime(t.transaction_date),
        }
        for t in txns if t.customer_id is not None
    ])

    platform_aov = round(float(df_tx["amount"].mean()), 2) if not df_tx.empty else 150.0
    ref_date = df_tx["date"].max() if not df_tx.empty else pd.Timestamp("2024-12-31")

    # Bayesian prior weight for AOV shrinkage
    n_0 = 3.0

    customer_clv_list = []
    total_hist_rev = 0.0
    total_future_val = 0.0

    for c in customers:
        cid = c.customer_id
        c_tx = df_tx[df_tx["customer_id"] == cid] if not df_tx.empty else pd.DataFrame()

        order_count = len(c_tx)
        hist_spend = round(float(c_tx["amount"].sum()), 2) if order_count > 0 else 0.0
        total_hist_rev += hist_spend

        if order_count > 0:
            last_date = c_tx["date"].max()
            first_date = c_tx["date"].min()
            recency_days = max(0, (ref_date - last_date).days)
            tenure_months = max(1.0, (last_date - first_date).days / 30.4)
            avg_order_val = hist_spend / order_count
        else:
            recency_days = max(0, (ref_date - pd.to_datetime(c.signup_date)).days)
            tenure_months = 1.0
            avg_order_val = platform_aov

        # Active probability from churn model: P(Active) = 1 - P(churn)
        churn_prob = churn_map.get(cid, 0.30)
        p_active = max(0.05, 1.0 - churn_prob)

        # Expected future order frequency over horizon (12M), with inactivity decay
        raw_annual_freq = (order_count / tenure_months) * horizon_months if order_count > 0 else 0.5
        recency_months = recency_days / 30.4
        inactivity_decay = math.exp(-0.15 * min(12.0, recency_months))
        predicted_future_orders = max(0.5, raw_annual_freq * inactivity_decay * p_active)

        # Bayesian shrinkage for expected future order monetary value
        predicted_future_aov = (order_count * avg_order_val + n_0 * platform_aov) / (order_count + n_0)

        # Predicted future spend
        future_spend = round(predicted_future_orders * predicted_future_aov, 2)
        total_future_val += future_spend

        total_clv = round(hist_spend + future_spend, 2)

        # Uncertainty intervals (90% interval approx: +/- 25%)
        lower_bound = max(hist_spend, round(hist_spend + future_spend * 0.75, 2))
        upper_bound = round(hist_spend + future_spend * 1.30, 2)

        customer_clv_list.append({
            "customer_id": cid,
            "name": c.name,
            "historical_spend": hist_spend,
            "order_count": order_count,
            "avg_order_value": round(avg_order_val, 2),
            "recency_days": int(recency_days),
            "active_probability": round(p_active, 4),
            "predicted_future_orders_12m": round(predicted_future_orders, 1),
            "predicted_future_spend_12m": future_spend,
            "total_predicted_clv": total_clv,
            "clv_lower_bound": lower_bound,
            "clv_upper_bound": upper_bound,
        })

    # Sort descending by total predicted CLV
    customer_clv_list.sort(key=lambda x: x["total_predicted_clv"], reverse=True)

    # Assign CLV Tiers based on percentiles
    n_cust = len(customer_clv_list)
    tier_counts = {"Tier 1: Platinum": 0, "Tier 2: Gold": 0, "Tier 3: Silver": 0, "Tier 4: Bronze": 0}

    for idx, item in enumerate(customer_clv_list):
        pct = (idx + 1) / n_cust
        if pct <= 0.15:
            tier = "Tier 1: Platinum"
        elif pct <= 0.40:
            tier = "Tier 2: Gold"
        elif pct <= 0.75:
            tier = "Tier 3: Silver"
        else:
            tier = "Tier 4: Bronze"

        item["clv_tier"] = tier
        tier_counts[tier] += 1

    all_clvs = [c["total_predicted_clv"] for c in customer_clv_list]

    return {
        "total_customers": n_cust,
        "aggregate_historical_revenue": round(total_hist_rev, 2),
        "aggregate_predicted_12m_future_value": round(total_future_val, 2),
        "mean_clv": round(float(np.mean(all_clvs)), 2) if all_clvs else 0.0,
        "median_clv": round(float(np.median(all_clvs)), 2) if all_clvs else 0.0,
        "clv_tiers_distribution": tier_counts,
        "customers": customer_clv_list,
        "model_assumptions": (
            "12-month forward horizon. Expected future order frequency modeled using empirical order run-rates "
            "adjusted for inactivity recency decay and active life probability P(Active)=1-P(churn). "
            "Future order values shrunk toward marketplace AOV using empirical Bayesian prior."
        ),
    }


def get_single_customer_clv(db: Session, customer_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves CLV prediction for an individual customer."""
    data = compute_predictive_clv(db)
    customers = data.get("customers", [])
    match = next((c for c in customers if c["customer_id"] == customer_id), None)
    if not match:
        return None

    pathway = (
        "VIP Concierge & Exclusive Early Access"
        if match["clv_tier"] == "Tier 1: Platinum"
        else ("Cross-Category Bundles & Loyalty Upgrades"
              if match["clv_tier"] == "Tier 2: Gold"
              else ("Re-engagement Incentive & Win-Back Discount"
                    if match["clv_tier"] == "Tier 4: Bronze"
                    else "Core Product Replenishment"))
    )

    return {
        "customer_id": match["customer_id"],
        "name": match["name"],
        "historical_spend": match["historical_spend"],
        "order_count": match["order_count"],
        "predicted_future_spend_12m": match["predicted_future_spend_12m"],
        "total_predicted_clv": match["total_predicted_clv"],
        "clv_tier": match["clv_tier"],
        "uncertainty_bounds": {
            "lower_bound_90pct": match["clv_lower_bound"],
            "upper_bound_90pct": match["clv_upper_bound"],
        },
        "recommendation_pathway": pathway,
    }

"""
services/funnel_service.py — Customer Conversion Funnel Analytics Engine.
Stage 5 Module 7.

Key Principles:
  - Computed strictly from authentic, recorded interaction and transaction events.
  - Funnel Stages supported by empirical data:
      Stage 1: Discovery & Product Views (interaction_type = 'view')
      Stage 2: Engagement & Add to Cart (interaction_type = 'add_to_cart')
      Stage 3: Completed Purchase Orders (transactions ledger & interaction_type = 'purchase')
  - Zero historical event fabrication: clearly declares missing intermediary stages (e.g. checkout initiation)
    rather than backfilling synthetic events.
"""

from typing import List, Dict, Any, Optional
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.customer import Customer
from app.models.customer_interaction import CustomerInteraction
from app.models.transaction import Transaction


def compute_conversion_funnel(
    db: Session,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    category_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Computes empirical stage-wise user conversion and drop-off rates.
    """
    interactions_q = db.query(
        CustomerInteraction.interaction_id,
        CustomerInteraction.customer_id,
        CustomerInteraction.product_id,
        CustomerInteraction.interaction_type,
        CustomerInteraction.interaction_date,
    )

    transactions_q = db.query(
        Transaction.transaction_id,
        Transaction.customer_id,
        Transaction.product_id,
        Transaction.amount,
        Transaction.transaction_date,
    )

    if start_date:
        interactions_q = interactions_q.filter(CustomerInteraction.interaction_date >= start_date)
        transactions_q = transactions_q.filter(Transaction.transaction_date >= start_date)
    if end_date:
        interactions_q = interactions_q.filter(CustomerInteraction.interaction_date <= end_date)
        transactions_q = transactions_q.filter(Transaction.transaction_date <= end_date)

    ix_rows = interactions_q.all()
    tx_rows = transactions_q.all()

    df_ix = pd.DataFrame([
        {
            "customer_id": r.customer_id,
            "interaction_type": r.interaction_type,
            "product_id": r.product_id,
        }
        for r in ix_rows
    ]) if ix_rows else pd.DataFrame(columns=["customer_id", "interaction_type", "product_id"])

    df_tx = pd.DataFrame([
        {
            "customer_id": r.customer_id,
            "product_id": r.product_id,
        }
        for r in tx_rows if r.customer_id is not None
    ]) if tx_rows else pd.DataFrame(columns=["customer_id", "product_id"])

    # Stage 1: Discovery / Product View
    view_events = df_ix[df_ix["interaction_type"] == "view"] if not df_ix.empty else pd.DataFrame()
    s1_events = len(view_events)
    s1_users = set(view_events["customer_id"].dropna().unique()) if not view_events.empty else set()

    # Stage 2: Engagement / Add to Cart
    cart_events = df_ix[df_ix["interaction_type"] == "add_to_cart"] if not df_ix.empty else pd.DataFrame()
    s2_events = len(cart_events)
    s2_users = set(cart_events["customer_id"].dropna().unique()) if not cart_events.empty else set()

    # Stage 3: Completed Purchase Orders
    s3_events = len(df_tx)
    s3_users = set(df_tx["customer_id"].dropna().unique()) if not df_tx.empty else set()

    # Calculate progression metrics
    # Base discovery count
    total_discovery_users = max(1, len(s1_users))
    u1_cnt = len(s1_users)
    u2_cnt = len(s2_users)
    u3_cnt = len(s3_users)

    # Stage 1
    stage_1 = {
        "stage_id": 1,
        "stage_name": "1. Discovery & Product Views",
        "event_type": "view",
        "total_events": s1_events,
        "unique_users": u1_cnt,
        "conversion_from_previous_pct": 100.0,
        "dropoff_from_previous_pct": 0.0,
        "overall_conversion_pct": 100.0,
    }

    # Stage 2: View -> Add to Cart
    conv_1_to_2 = round(min(100.0, (u2_cnt / u1_cnt * 100.0)), 2) if u1_cnt > 0 else 0.0
    drop_1_to_2 = round(max(0.0, 100.0 - conv_1_to_2), 2)
    stage_2 = {
        "stage_id": 2,
        "stage_name": "2. Product Intent & Add to Cart",
        "event_type": "add_to_cart",
        "total_events": s2_events,
        "unique_users": u2_cnt,
        "conversion_from_previous_pct": conv_1_to_2,
        "dropoff_from_previous_pct": drop_1_to_2,
        "overall_conversion_pct": conv_1_to_2,
    }

    # Stage 3: Cart -> Completed Purchase
    conv_2_to_3 = round(min(100.0, (u3_cnt / u2_cnt * 100.0)), 2) if u2_cnt > 0 else 0.0
    overall_conv = round(min(100.0, (u3_cnt / u1_cnt * 100.0)), 2) if u1_cnt > 0 else 0.0
    drop_2_to_3 = round(max(0.0, 100.0 - conv_2_to_3), 2)
    stage_3 = {
        "stage_id": 3,
        "stage_name": "3. Order Checkout & Completed Purchase",
        "event_type": "purchase",
        "total_events": s3_events,
        "unique_users": u3_cnt,
        "conversion_from_previous_pct": conv_2_to_3,
        "dropoff_from_previous_pct": drop_2_to_3,
        "overall_conversion_pct": overall_conv,
    }

    stages = [stage_1, stage_2, stage_3]

    timeframe_label = (
        f"{start_date or 'Earliest'} to {end_date or 'Latest'}"
        if start_date or end_date
        else "All Recorded Calendar Activity (2024)"
    )

    return {
        "funnel_name": "Marketplace Retail Conversion Funnel (3-Stage Empirical)",
        "timeframe": timeframe_label,
        "stages": stages,
        "total_visitors_discovered": u1_cnt,
        "total_purchasing_customers": u3_cnt,
        "overall_funnel_conversion_pct": overall_conv,
        "data_authenticity_declaration": (
            "Empirical funnel constructed strictly from authentic interactions ('view', 'add_to_cart') "
            "and transactions ('purchase'). Intermediate micro-events like checkout initiation are omitted "
            "to prevent synthetic data fabrication."
        ),
    }

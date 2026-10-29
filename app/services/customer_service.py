"""
services/customer_service.py — Business logic and ML models for Customer Analytics.

Features:
  1. Customer Purchasing Behavior & RFM Feature Engineering.
  2. K-Means Customer Segmentation with StandardScaler.
  3. Silhouette Score Evaluation & Cluster Profiling.
  4. Marketplace Customer Lifetime Value & Cohort Summary.
"""

from datetime import datetime
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score, silhouette_samples

from app.models.customer import Customer
from app.models.transaction import Transaction


def get_customer_summary(db: Session) -> dict:
    """
    Computes overall customer base KPIs:
      - Total registered customers
      - Active customers (purchased in last 90 days)
      - Repeat customers (placed >= 2 orders)
      - Repeat purchase rate (%)
      - Average customer lifetime spend
      - Average order value (AOV) across all customer transactions
    """
    total_customers = db.query(func.count(Customer.customer_id)).scalar() or 0
    if total_customers == 0:
        return {
            "total_customers": 0,
            "active_customers_90d": 0,
            "repeat_customers": 0,
            "repeat_purchase_rate_pct": 0.0,
            "avg_customer_spend": 0.0,
            "avg_order_value": 0.0,
            "total_customer_revenue": 0.0,
        }

    # Query customer transactions
    txns = (
        db.query(
            Transaction.customer_id,
            Transaction.amount,
            Transaction.transaction_date,
        )
        .filter(Transaction.customer_id.isnot(None))
        .all()
    )

    if not txns:
        return {
            "total_customers": total_customers,
            "active_customers_90d": 0,
            "repeat_customers": 0,
            "repeat_purchase_rate_pct": 0.0,
            "avg_customer_spend": 0.0,
            "avg_order_value": 0.0,
            "total_customer_revenue": 0.0,
        }

    df = pd.DataFrame([
        {"customer_id": t.customer_id, "amount": float(t.amount), "txn_date": t.transaction_date}
        for t in txns
    ])

    # Reference max date
    max_date = df["txn_date"].max()
    ninety_days_ago = max_date - pd.Timedelta(days=90)

    # Aggregations per customer
    grouped = df.groupby("customer_id").agg(
        order_count=("amount", "count"),
        total_spend=("amount", "sum"),
        last_purchase=("txn_date", "max"),
    ).reset_index()

    active_count = int((grouped["last_purchase"] >= ninety_days_ago).sum())
    repeat_count = int((grouped["order_count"] >= 2).sum())
    repeat_rate = round((repeat_count / total_customers) * 100.0, 2)
    total_revenue = round(float(df["amount"].sum()), 2)
    avg_customer_spend = round(total_revenue / total_customers, 2)
    avg_order_value = round(float(df["amount"].mean()), 2)

    return {
        "total_customers": total_customers,
        "active_customers_90d": active_count,
        "repeat_customers": repeat_count,
        "repeat_purchase_rate_pct": repeat_rate,
        "avg_customer_spend": avg_customer_spend,
        "avg_order_value": avg_order_value,
        "total_customer_revenue": total_revenue,
    }


def compute_rfm_metrics(db: Session) -> list[dict]:
    """
    Computes Recency, Frequency, Monetary (RFM), and Average Order Value (AOV)
    for every registered customer.
    """
    customers = db.query(Customer).order_by(Customer.customer_id.asc()).all()
    if not customers:
        return []

    txns = (
        db.query(
            Transaction.customer_id,
            Transaction.amount,
            Transaction.transaction_date,
        )
        .filter(Transaction.customer_id.isnot(None))
        .all()
    )

    if not txns:
        return [
            {
                "customer_id": c.customer_id,
                "name": c.name,
                "email": c.email,
                "city": c.city,
                "recency_days": 999,
                "frequency": 0,
                "monetary": 0.0,
                "avg_order_value": 0.0,
            }
            for c in customers
        ]

    df = pd.DataFrame([
        {"customer_id": t.customer_id, "amount": float(t.amount), "txn_date": t.transaction_date}
        for t in txns
    ])

    ref_date = df["txn_date"].max()

    rfm_df = (
        df.groupby("customer_id")
        .agg(
            recency_days=("txn_date", lambda dates: int((ref_date - dates.max()).days)),
            frequency=("amount", "count"),
            monetary=("amount", "sum"),
            avg_order_value=("amount", "mean"),
        )
        .reset_index()
    )

    rfm_map = {row["customer_id"]: row for _, row in rfm_df.iterrows()}

    result = []
    for c in customers:
        data = rfm_map.get(c.customer_id)
        if data is not None:
            result.append({
                "customer_id": c.customer_id,
                "name": c.name,
                "email": c.email,
                "city": c.city,
                "recency_days": int(data["recency_days"]),
                "frequency": int(data["frequency"]),
                "monetary": round(float(data["monetary"]), 2),
                "avg_order_value": round(float(data["avg_order_value"]), 2),
            })
        else:
            result.append({
                "customer_id": c.customer_id,
                "name": c.name,
                "email": c.email,
                "city": c.city,
                "recency_days": 999,
                "frequency": 0,
                "monetary": 0.0,
                "avg_order_value": 0.0,
            })
    return result


def segment_customers(db: Session, n_clusters: int | None = None) -> dict:
    """
    Performs K-Means clustering on Customer RFM Behavioral Features.

    Methodology:
      1. Computes RFM metrics (Recency, Frequency, Monetary, AOV) for active customers.
      2. Scales features using StandardScaler to ensure unit variance.
      3. Automatically selects optimal k (between 2 and 5) using silhouette scores if n_clusters is None.
      4. Fits KMeans(n_clusters=k, random_state=42, n_init=10).
      5. Evaluates cluster quality using sklearn.metrics.silhouette_score.
      6. Labels each cluster with business personas based on relative centroid profiles:
         - 'Champions / VIP' (High monetary, high frequency, recent)
         - 'Loyal Regulars' (Moderate spend, steady frequency, recent)
         - 'At-Risk / Lapsed' (High recency / dormant, moderate historical spend)
         - 'New / Occasional' (Low frequency, small monetary)
    """
    rfm_list = compute_rfm_metrics(db)
    # Filter customers with at least 1 order for behavioral clustering
    active_rfm = [c for c in rfm_list if c["frequency"] > 0]

    if len(active_rfm) < 4:
        return {
            "n_clusters": 0,
            "silhouette_score": 0.0,
            "message": "Insufficient active customers (< 4) to perform K-Means clustering.",
            "cluster_profiles": [],
            "customers": rfm_list,
        }

    df = pd.DataFrame(active_rfm)
    feature_cols = ["recency_days", "frequency", "monetary", "avg_order_value"]
    X = df[feature_cols].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Determine optimal k if not provided
    max_k = min(5, len(active_rfm) - 1)
    if n_clusters is None or n_clusters < 2 or n_clusters > max_k:
        best_k = 3
        best_sil = -1.0
        for k_test in range(2, max_k + 1):
            km = KMeans(n_clusters=k_test, random_state=42, n_init=10)
            labels = km.fit_predict(X_scaled)
            sil = float(silhouette_score(X_scaled, labels))
            if sil > best_sil:
                best_sil = sil
                best_k = k_test
        n_clusters = best_k

    # Fit final K-Means
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    df["cluster"] = kmeans.fit_predict(X_scaled)

    # Compute overall and per-sample silhouette scores
    overall_silhouette = round(float(silhouette_score(X_scaled, df["cluster"])), 3)
    sample_sils = silhouette_samples(X_scaled, df["cluster"])
    df["silhouette"] = [round(float(s), 3) for s in sample_sils]

    # Analyze centroids to generate business persona names
    centroids = df.groupby("cluster")[feature_cols].mean()

    # Assign dynamic business personas based on centroids
    # Rank clusters by monetary spend and recency
    cluster_profiles = []
    persona_assignments = {}

    for c_id, row in centroids.iterrows():
        rec = row["recency_days"]
        freq = row["frequency"]
        mon = row["monetary"]
        c_size = int((df["cluster"] == c_id).sum())
        c_sil = round(float(df[df["cluster"] == c_id]["silhouette"].mean()), 3)

        # Profile heuristic
        if mon >= centroids["monetary"].quantile(0.70) and rec <= centroids["recency_days"].median():
            label = "Champions / VIP"
            desc = "High lifetime spend, frequent transactions, highly engaged recently."
        elif rec > centroids["recency_days"].quantile(0.60):
            label = "At-Risk / Lapsed"
            desc = "High days since last purchase; previously active but at risk of churn."
        elif freq >= centroids["frequency"].median():
            label = "Loyal Regulars"
            desc = "Consistent purchase frequency and steady order volume."
        else:
            label = "New / Occasional"
            desc = "Low purchase frequency, lower basket size, or recent onboarding."

        persona_assignments[c_id] = label
        cluster_profiles.append({
            "cluster_id": int(c_id),
            "segment_name": label,
            "description": desc,
            "customer_count": c_size,
            "avg_recency_days": round(float(rec), 1),
            "avg_frequency": round(float(freq), 1),
            "avg_monetary": round(float(mon), 2),
            "avg_order_value": round(float(row["avg_order_value"]), 2),
            "cluster_silhouette": c_sil,
        })

    df["segment_name"] = df["cluster"].map(persona_assignments)

    # Map back to full list
    active_dict = {row["customer_id"]: row for _, row in df.iterrows()}
    full_results = []
    for c in rfm_list:
        if c["customer_id"] in active_dict:
            row = active_dict[c["customer_id"]]
            c_copy = dict(c)
            c_copy["cluster"] = int(row["cluster"])
            c_copy["segment_name"] = row["segment_name"]
            c_copy["silhouette"] = row["silhouette"]
            full_results.append(c_copy)
        else:
            c_copy = dict(c)
            c_copy["cluster"] = -1
            c_copy["segment_name"] = "Inactive / No Purchases"
            c_copy["silhouette"] = 0.0
            full_results.append(c_copy)

    return {
        "n_clusters": n_clusters,
        "silhouette_score": overall_silhouette,
        "algorithm": "K-Means (StandardScaler normalized)",
        "cluster_profiles": sorted(cluster_profiles, key=lambda x: -x["avg_monetary"]),
        "customers": full_results,
    }

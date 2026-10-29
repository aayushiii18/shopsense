"""
services/recommendation_service.py — Personalized Product Recommendations & Offline Evaluation.

Algorithms:
  1. Item-Based Collaborative Filtering (Cosine Similarity on Customer Interaction Vectors).
  2. Interaction Weighting (views: 1.0, carts: 2.5, purchases: 4.0, ratings: 1.0-5.0).
  3. Top-N Recommendation Ranking with Cold-Start Popularity Fallback.
  4. Offline Evaluation Engine: Chronological Leave-20%-Out Interaction Holdout
     computing Precision@K, Recall@K, and Hit Rate.
"""

from collections import defaultdict
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.product import Product
from app.models.vendor import Vendor
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.models.customer_interaction import CustomerInteraction


def _load_interaction_dataframe(db: Session) -> pd.DataFrame:
    """
    Consolidates interactions from customer_interactions table and transactions table.
    Returns DataFrame: [customer_id, product_id, weight, date]
    """
    records = []

    # 1. Direct interactions
    ci_rows = db.query(CustomerInteraction).all()
    for row in ci_rows:
        records.append({
            "customer_id": row.customer_id,
            "product_id": row.product_id,
            "weight": float(row.interaction_weight),
            "date": row.interaction_date,
        })

    # 2. Transactions as implicit purchases (weight 4.0)
    tx_rows = db.query(Transaction).filter(Transaction.customer_id.isnot(None)).all()
    for row in tx_rows:
        records.append({
            "customer_id": row.customer_id,
            "product_id": row.product_id,
            "weight": 4.0,
            "date": row.transaction_date,
        })

    if not records:
        return pd.DataFrame(columns=["customer_id", "product_id", "weight", "date"])

    df = pd.DataFrame(records)
    # Deduplicate keeping maximum interaction weight per (customer, product, date)
    df = df.groupby(["customer_id", "product_id", "date"])["weight"].max().reset_index()
    return df


def get_popular_products(db: Session, top_n: int = 5) -> list[dict]:
    """
    Returns globally popular products based on transaction volume,
    used for cold-start recommendations.
    """
    sales = (
        db.query(
            Product.id,
            Product.name,
            Product.price,
            Product.category,
            Product.parent_category,
            Vendor.name.label("vendor_name"),
            func.coalesce(func.sum(Transaction.quantity), 0).label("units_sold"),
        )
        .join(Vendor, Product.vendor_id == Vendor.id)
        .outerjoin(Transaction, Product.id == Transaction.product_id)
        .group_by(Product.id, Vendor.name)
        .order_by(func.coalesce(func.sum(Transaction.quantity), 0).desc(), Product.id.asc())
        .limit(top_n)
        .all()
    )

    return [
        {
            "product_id": r.id,
            "product_name": r.name,
            "category": r.category,
            "parent_category": r.parent_category,
            "price": float(r.price),
            "vendor_name": r.vendor_name,
            "score": round(float(r.units_sold), 1),
            "recommendation_type": "Popularity / Best Seller (Cold Start)",
            "rationale": f"Top-selling product across the platform ({r.units_sold} units sold).",
        }
        for r in sales
    ]


def build_item_similarity_matrix(df: pd.DataFrame) -> tuple[dict, dict]:
    """
    Builds item-item cosine similarity matrix from customer interaction records.
    Returns:
        item_sim: dict[product_id, dict[other_product_id, similarity]]
        user_profiles: dict[customer_id, dict[product_id, weight]]
    """
    if df.empty:
        return {}, {}

    # Pivot customer x product matrix
    user_item = df.groupby(["customer_id", "product_id"])["weight"].max().unstack(fill_value=0.0)

    # Cosine similarity between product columns
    # Item vectors: columns of user_item
    item_cols = list(user_item.columns)
    item_matrix = user_item.values.T  # shape: (n_items, n_users)

    # Compute L2 norms
    norms = np.linalg.norm(item_matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1e-9
    normalized_matrix = item_matrix / norms

    # Similarity matrix: (n_items, n_items)
    sim_matrix = normalized_matrix @ normalized_matrix.T

    item_sim = defaultdict(dict)
    for i, p1 in enumerate(item_cols):
        for j, p2 in enumerate(item_cols):
            if i != j:
                item_sim[p1][p2] = float(sim_matrix[i, j])

    user_profiles = user_item.to_dict(orient="index")
    return item_sim, user_profiles


def get_personalized_recommendations(
    db: Session, customer_id: int, top_n: int = 5, exclude_purchased: bool = True
) -> dict:
    """
    Generates personalized Top-N product recommendations for a customer
    using Item-Based Collaborative Filtering. Falls back gracefully to popular products.
    """
    customer = db.query(Customer).filter_by(customer_id=customer_id).first()
    if not customer:
        raise ValueError(f"Customer {customer_id} not found.")

    df = _load_interaction_dataframe(db)
    if df.empty or customer_id not in df["customer_id"].values:
        # Cold-start fallback
        fallback = get_popular_products(db, top_n=top_n)
        return {
            "customer_id": customer_id,
            "customer_name": customer.name,
            "is_personalized": False,
            "recommendation_count": len(fallback),
            "recommendations": fallback,
        }

    item_sim, user_profiles = build_item_similarity_matrix(df)
    cust_profile = user_profiles.get(customer_id, {})
    interacted_products = {p for p, w in cust_profile.items() if w > 0}

    # Fetch catalog products
    all_products = {
        p.id: p
        for p in db.query(Product).join(Vendor, Product.vendor_id == Vendor.id).all()
    }

    # Candidate scoring: for each unrated product j, sum_i (sim(i, j) * rating_i) / sum_i (sim(i, j))
    candidate_scores = {}
    candidate_sources = {}

    for prod_id in all_products:
        if exclude_purchased and prod_id in interacted_products:
            continue

        weighted_sim_sum = 0.0
        sim_sum = 0.0
        strongest_source = None
        max_source_sim = 0.0

        for user_prod, user_rating in cust_profile.items():
            if user_rating > 0 and user_prod in item_sim and prod_id in item_sim[user_prod]:
                s = item_sim[user_prod][prod_id]
                if s > 0:
                    weighted_sim_sum += s * user_rating
                    sim_sum += s
                    if s > max_source_sim:
                        max_source_sim = s
                        strongest_source = user_prod

        if sim_sum > 0:
            candidate_scores[prod_id] = weighted_sim_sum / sim_sum
            candidate_sources[prod_id] = strongest_source

    if not candidate_scores:
        # Fallback to popular products excluding already purchased
        popular = get_popular_products(db, top_n=top_n + len(interacted_products))
        filtered_popular = [p for p in popular if p["product_id"] not in interacted_products][:top_n]
        return {
            "customer_id": customer_id,
            "customer_name": customer.name,
            "is_personalized": False,
            "recommendation_count": len(filtered_popular),
            "recommendations": filtered_popular,
        }

    # Rank top candidates
    sorted_candidates = sorted(candidate_scores.items(), key=lambda x: x[1], reverse=True)[:top_n]

    recommendations = []
    for prod_id, score in sorted_candidates:
        p = all_products.get(prod_id)
        if not p:
            continue

        src_id = candidate_sources.get(prod_id)
        src_name = all_products[src_id].name if src_id in all_products else None
        rationale = (
            f"Frequently explored alongside {src_name}."
            if src_name
            else "High compatibility with your browsing and purchase habits."
        )

        recommendations.append({
            "product_id": p.id,
            "product_name": p.name,
            "category": p.category,
            "parent_category": p.parent_category,
            "price": float(p.price),
            "vendor_name": p.vendor.name if p.vendor else "StockPilot Vendor",
            "score": round(float(score), 2),
            "recommendation_type": "Personalized Collaborative Filtering",
            "rationale": rationale,
        })

    return {
        "customer_id": customer_id,
        "customer_name": customer.name,
        "is_personalized": True,
        "recommendation_count": len(recommendations),
        "recommendations": recommendations,
    }


def evaluate_recommendation_engine(db: Session, k: int = 5) -> dict:
    """
    Offline Evaluation of Recommendation Engine using Chronological Leave-20%-Out Interaction Holdout.

    Methodology:
      1. For each customer with >= 3 distinct interactions, sort chronologically.
      2. Hold out the final 20% of interactions as test set T_test.
      3. Fit Item-Based Collaborative Filtering model on earlier 80% interactions T_train.
      4. For each evaluation user, generate Top-K recommendations.
      5. Metrics:
         - Precision@K = |Top-K intersected with T_test| / K
         - Recall@K = |Top-K intersected with T_test| / |T_test|
         - Hit Rate@K = 1 if |Top-K intersected with T_test| > 0 else 0
    """
    df = _load_interaction_dataframe(db)
    if df.empty:
        return {
            "evaluation_k": k,
            "sample_size_users": 0,
            "mean_precision_at_k": 0.0,
            "mean_recall_at_k": 0.0,
            "hit_rate_at_k": 0.0,
            "message": "No interactions available for offline evaluation.",
        }

    # Group by customer and chronological order
    df = df.sort_values(["customer_id", "date"]).reset_index(drop=True)

    train_records = []
    test_sets = {}  # customer_id -> set of product_ids in test holdout

    user_groups = df.groupby("customer_id")
    eval_users = []

    for cust_id, group in user_groups:
        unique_prods = group["product_id"].unique()
        if len(unique_prods) >= 3:
            # Chronological 80/20 split
            n_items = len(group)
            split_idx = max(2, int(n_items * 0.8))
            train_part = group.iloc[:split_idx]
            test_part = group.iloc[split_idx:]

            test_prods = set(test_part["product_id"].unique()) - set(train_part["product_id"].unique())
            if test_prods:
                train_records.append(train_part)
                test_sets[cust_id] = test_prods
                eval_users.append(cust_id)
            else:
                train_records.append(group)
        else:
            train_records.append(group)

    if not eval_users or not train_records:
        return {
            "evaluation_k": k,
            "sample_size_users": 0,
            "mean_precision_at_k": 0.0,
            "mean_recall_at_k": 0.0,
            "hit_rate_at_k": 0.0,
            "message": "Insufficient users with >= 3 distinct chronological interactions to evaluate.",
        }

    df_train = pd.concat(train_records, ignore_index=True)
    item_sim, user_profiles = build_item_similarity_matrix(df_train)

    precisions = []
    recalls = []
    hits = []

    all_product_ids = list(df["product_id"].unique())

    for cust_id in eval_users:
        t_test = test_sets[cust_id]
        profile = user_profiles.get(cust_id, {})
        interacted_in_train = {p for p, w in profile.items() if w > 0}

        # Predict scores for unobserved products in training
        candidate_scores = {}
        for p_cand in all_product_ids:
            if p_cand in interacted_in_train:
                continue

            num = 0.0
            denom = 0.0
            for p_user, rating in profile.items():
                if rating > 0 and p_user in item_sim and p_cand in item_sim[p_user]:
                    sim = item_sim[p_user][p_cand]
                    if sim > 0:
                        num += sim * rating
                        denom += sim
            score = (num / denom) if denom > 0 else 0.0
            candidate_scores[p_cand] = score

        # Top-K recommendations
        top_k = [p for p, _ in sorted(candidate_scores.items(), key=lambda x: x[1], reverse=True)[:k]]

        # Compute matches
        matches = len(set(top_k) & t_test)
        prec = matches / float(k)
        rec = matches / float(len(t_test))
        hit = 1.0 if matches > 0 else 0.0

        precisions.append(prec)
        recalls.append(rec)
        hits.append(hit)

    mean_precision = round(float(np.mean(precisions)), 4)
    mean_recall = round(float(np.mean(recalls)), 4)
    hit_rate = round(float(np.mean(hits)), 4)

    return {
        "evaluation_k": k,
        "sample_size_users": len(eval_users),
        "mean_precision_at_k": mean_precision,
        "mean_recall_at_k": mean_recall,
        "hit_rate_at_k": hit_rate,
        "split_method": "Chronological Leave-20%-Out Holdout (Zero Lookahead Bias)",
    }

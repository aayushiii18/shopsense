"""
tests/test_stage5_intelligence.py — Comprehensive test suite for Stage 5:
Customer Retention & Advanced Intelligence.

Covers:
  1. Supervised Churn: Zero target lookahead, temporal cutoff separation, 5-fold CV, explainability.
  2. Customer Cohort Retention: Signup month cohorts across 12 calendar activity months.
  3. Predictive CLV: Distinguishing historical spend from 12M forward value, Bayesian shrinkage AOV, tiers, bounds.
  4. Catalog Normalizer: Canonical taxonomy, unit extraction, brand inference, duplicate detection, non-destructive.
  5. Hybrid Recommender: CF + Content weighting, verified in-stock guard, chronological holdout evaluation.
  6. Conversion Funnel: Empirical View -> Cart -> Purchase drop-off rates and authenticity declaration.
  7. Offer Strategy & Stock Impact: Segment mapping, 3-tier elasticity, safety stock boundary enforcement.
  8. API Endpoints: Status codes, schema compliance, and 404 handling.
"""

from datetime import datetime
import pytest
import pandas as pd

from app.models.vendor import Vendor
from app.models.product import Product
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.models.inventory import Inventory
from app.models.customer_interaction import CustomerInteraction

from app.services.churn_service import _extract_churn_dataset, train_and_evaluate_churn_model, get_single_customer_churn
from app.services.cohort_service import compute_cohort_retention
from app.services.clv_service import compute_predictive_clv, get_single_customer_clv
from app.services.catalog_normalizer import normalize_catalog, get_single_product_normalized, extract_unit_and_measurement, normalize_category
from app.services.hybrid_recommender import _prepare_hybrid_context, get_hybrid_recommendations, evaluate_hybrid_engine
from app.services.funnel_service import compute_conversion_funnel
from app.services.offer_service import generate_personalized_offer_strategy, evaluate_stock_impact_safety, resolve_price_elasticity


def _seed_stage5_test_data(db):
    """Seeds a representative dataset of 10 customers (6 active, 4 churned), vendors, products, inventory, txns, and interactions."""
    # 1. Vendor
    v = Vendor(id=1, name="Sound & Vision Co", email="contact@soundvision.com", phone="+1-555-0100", commission_tier="TIER_STANDARD", status="ACTIVE")
    db.add(v)
    db.flush()

    # 2. Products
    p1 = Product(id=1, name="Studio Wireless Headphones (1.2 kg)", category="Headphones", price=150.0, cost_price=90.0, vendor_id=1, description="High performance studio wireless headphones 1.2 kg weight.")
    p2 = Product(id=2, name="Ultra 27-inch Display Monitor", category="Monitors", price=300.0, cost_price=180.0, vendor_id=1, description="Ultra clear 27-inch desktop monitor display.")
    p3 = Product(id=3, name="Duplicate Studio Wireless Headphones 1.2 kg", category="Audio", price=150.0, cost_price=90.0, vendor_id=1, description="High performance studio wireless headphones 1.2 kg weight.")
    db.add_all([p1, p2, p3])
    db.flush()

    # 3. Inventory: p1 has ample stock (40 vs 15), p2 has constrained stock (12 vs 10), p3 is out of stock (0 vs 5)
    inv1 = Inventory(product_id=1, current_stock=40, reorder_level=15)
    inv2 = Inventory(product_id=2, current_stock=12, reorder_level=10)
    inv3 = Inventory(product_id=3, current_stock=0, reorder_level=5)
    db.add_all([inv1, inv2, inv3])
    db.flush()

    # 4. Customers: 10 customers signed up Jun–Dec 2023
    customers = [
        Customer(customer_id=1, name="Aarav Sharma", email="aarav@example.com", signup_date=datetime(2023, 6, 15)),
        Customer(customer_id=2, name="Diya Patel", email="diya@example.com", signup_date=datetime(2023, 6, 20)),
        Customer(customer_id=3, name="Rohan Mehta", email="rohan@example.com", signup_date=datetime(2023, 7, 10)),
        Customer(customer_id=4, name="Priya Singh", email="priya@example.com", signup_date=datetime(2023, 7, 25)),
        Customer(customer_id=5, name="Amit Kumar", email="amit@example.com", signup_date=datetime(2023, 8, 5)),
        Customer(customer_id=6, name="Neha Gupta", email="neha@example.com", signup_date=datetime(2023, 8, 18)),
        Customer(customer_id=7, name="Karan Verma", email="karan@example.com", signup_date=datetime(2023, 9, 12)),
        Customer(customer_id=8, name="Sneha Rao", email="sneha@example.com", signup_date=datetime(2023, 9, 30)),
        Customer(customer_id=9, name="Vikram Das", email="vikram@example.com", signup_date=datetime(2023, 10, 15)),
        Customer(customer_id=10, name="Ananya Sen", email="ananya@example.com", signup_date=datetime(2023, 11, 20)),
    ]
    db.add_all(customers)
    db.flush()

    # 5. Transactions:
    # Active group (c1 to c6): has orders in Jan–Sep AND Oct–Dec
    txns = []
    # c1: active
    txns.append(Transaction(customer_id=1, product_id=1, vendor_id=1, quantity=2, unit_price=150.0, amount=300.0, transaction_date=datetime(2024, 2, 10)))
    txns.append(Transaction(customer_id=1, product_id=2, vendor_id=1, quantity=1, unit_price=300.0, amount=300.0, transaction_date=datetime(2024, 6, 15)))
    txns.append(Transaction(customer_id=1, product_id=1, vendor_id=1, quantity=1, unit_price=150.0, amount=150.0, transaction_date=datetime(2024, 11, 20)))

    # c2: active
    txns.append(Transaction(customer_id=2, product_id=2, vendor_id=1, quantity=1, unit_price=300.0, amount=300.0, transaction_date=datetime(2024, 3, 5)))
    txns.append(Transaction(customer_id=2, product_id=1, vendor_id=1, quantity=1, unit_price=150.0, amount=150.0, transaction_date=datetime(2024, 10, 12)))

    # c3: active
    txns.append(Transaction(customer_id=3, product_id=1, vendor_id=1, quantity=2, unit_price=150.0, amount=300.0, transaction_date=datetime(2024, 4, 1)))
    txns.append(Transaction(customer_id=3, product_id=1, vendor_id=1, quantity=1, unit_price=150.0, amount=150.0, transaction_date=datetime(2024, 11, 5)))

    # c4: active
    txns.append(Transaction(customer_id=4, product_id=2, vendor_id=1, quantity=1, unit_price=300.0, amount=300.0, transaction_date=datetime(2024, 5, 18)))
    txns.append(Transaction(customer_id=4, product_id=2, vendor_id=1, quantity=1, unit_price=300.0, amount=300.0, transaction_date=datetime(2024, 12, 10)))

    # c5: active
    txns.append(Transaction(customer_id=5, product_id=1, vendor_id=1, quantity=1, unit_price=150.0, amount=150.0, transaction_date=datetime(2024, 1, 20)))
    txns.append(Transaction(customer_id=5, product_id=1, vendor_id=1, quantity=1, unit_price=150.0, amount=150.0, transaction_date=datetime(2024, 10, 28)))

    # c6: active
    txns.append(Transaction(customer_id=6, product_id=2, vendor_id=1, quantity=1, unit_price=300.0, amount=300.0, transaction_date=datetime(2024, 7, 14)))
    txns.append(Transaction(customer_id=6, product_id=2, vendor_id=1, quantity=1, unit_price=300.0, amount=300.0, transaction_date=datetime(2024, 11, 15)))

    # Churned group (c7 to c10): has orders ONLY in Jan–Sep, 0 in Oct–Dec
    txns.append(Transaction(customer_id=7, product_id=1, vendor_id=1, quantity=1, unit_price=150.0, amount=150.0, transaction_date=datetime(2024, 2, 22)))
    txns.append(Transaction(customer_id=8, product_id=2, vendor_id=1, quantity=1, unit_price=300.0, amount=300.0, transaction_date=datetime(2024, 3, 18)))
    txns.append(Transaction(customer_id=9, product_id=1, vendor_id=1, quantity=1, unit_price=150.0, amount=150.0, transaction_date=datetime(2024, 4, 25)))
    txns.append(Transaction(customer_id=10, product_id=2, vendor_id=1, quantity=1, unit_price=300.0, amount=300.0, transaction_date=datetime(2024, 5, 30)))

    db.add_all(txns)
    db.flush()

    # 6. Customer Interactions spanning pre- and post-cutoff
    interactions = [
        # c1 interactions (pre and post cutoff)
        CustomerInteraction(customer_id=1, product_id=1, interaction_type="view", interaction_weight=1.0, interaction_date=datetime(2024, 2, 9)),
        CustomerInteraction(customer_id=1, product_id=1, interaction_type="add_to_cart", interaction_weight=3.0, interaction_date=datetime(2024, 2, 10)),
        CustomerInteraction(customer_id=1, product_id=1, interaction_type="purchase", interaction_weight=5.0, interaction_date=datetime(2024, 2, 10)),
        CustomerInteraction(customer_id=1, product_id=2, interaction_type="view", interaction_weight=1.0, interaction_date=datetime(2024, 6, 14)),
        CustomerInteraction(customer_id=1, product_id=2, interaction_type="purchase", interaction_weight=5.0, interaction_date=datetime(2024, 6, 15)),
        CustomerInteraction(customer_id=1, product_id=1, interaction_type="purchase", interaction_weight=5.0, interaction_date=datetime(2024, 11, 20)),

        # c2 interactions (pre and post cutoff)
        CustomerInteraction(customer_id=2, product_id=2, interaction_type="view", interaction_weight=1.0, interaction_date=datetime(2024, 3, 4)),
        CustomerInteraction(customer_id=2, product_id=2, interaction_type="purchase", interaction_weight=5.0, interaction_date=datetime(2024, 3, 5)),
        CustomerInteraction(customer_id=2, product_id=1, interaction_type="view", interaction_weight=1.0, interaction_date=datetime(2024, 10, 11)),
        CustomerInteraction(customer_id=2, product_id=1, interaction_type="purchase", interaction_weight=5.0, interaction_date=datetime(2024, 10, 12)),

        # c7 interaction (pre cutoff)
        CustomerInteraction(customer_id=7, product_id=1, interaction_type="view", interaction_weight=1.0, interaction_date=datetime(2024, 2, 21)),
        CustomerInteraction(customer_id=7, product_id=1, interaction_type="purchase", interaction_weight=5.0, interaction_date=datetime(2024, 2, 22)),
    ]
    db.add_all(interactions)
    db.commit()


# ── 1. Customer Churn Prediction Tests ────────────────────────────────────────

def test_churn_temporal_separation_and_zero_lookahead(db_session):
    """Verifies that features are strictly computed <= 2024-09-30 and targets > 2024-09-30."""
    _seed_stage5_test_data(db_session)
    df = _extract_churn_dataset(db_session)

    assert not df.empty
    assert len(df) == 10

    # Customer 1 placed 2 orders in obs window (Jan–Sep) and 1 in outcome window (Nov)
    c1_row = df[df["customer_id"] == 1].iloc[0]
    assert c1_row["frequency_obs"] == 2
    assert c1_row["monetary_obs"] == 600.0
    assert c1_row["actual_churn"] == 0  # Retained

    # Customer 7 placed 1 order in obs window and 0 in outcome window
    c7_row = df[df["customer_id"] == 7].iloc[0]
    assert c7_row["frequency_obs"] == 1
    assert c7_row["monetary_obs"] == 150.0
    assert c7_row["actual_churn"] == 1  # Churned

    # Total churn distribution in seeded dataset: 6 active, 4 churned
    assert (df["actual_churn"] == 1).sum() == 4
    assert (df["actual_churn"] == 0).sum() == 6


def test_churn_model_evaluation_and_explainability(db_session):
    """Verifies stratified cross-validation, metrics calculation, and explainability factors."""
    _seed_stage5_test_data(db_session)
    res = train_and_evaluate_churn_model(db_session)

    assert "metrics" in res
    m = res["metrics"]
    assert m["total_customers"] == 10
    assert m["active_count"] == 6
    assert m["churned_count"] == 4
    assert 0.0 <= m["roc_auc_mean"] <= 1.0
    assert "confusion_matrix" in m
    assert "comparison_baseline" in m

    # Explainability checks
    assert len(res["customers"]) == 10
    for cust in res["customers"]:
        assert 0.0 <= cust["churn_probability"] <= 1.0
        assert cust["risk_category"] in ("HIGH", "MEDIUM", "LOW")
        assert cust["predicted_churn"] in (0, 1)
        assert isinstance(cust["contributing_factors"], list)


def test_churn_single_customer_retrieval(db_session):
    """Tests retrieving churn explanation for an individual customer."""
    _seed_stage5_test_data(db_session)
    res = get_single_customer_churn(db_session, customer_id=1)
    assert res is not None
    assert res["customer_id"] == 1
    assert res["risk_category"] in ("HIGH", "MEDIUM", "LOW")

    # Non-existent customer
    missing = get_single_customer_churn(db_session, customer_id=999)
    assert missing is None


# ── 2. Customer Cohort Retention Tests ────────────────────────────────────────

def test_cohort_retention_computation(db_session):
    """Verifies monthly cohort retention percentages across calendar months 2024."""
    _seed_stage5_test_data(db_session)
    res = compute_cohort_retention(db_session, cohort_type="signup_month")

    assert res["total_cohorts"] >= 1
    assert "cohorts" in res
    assert "average_retention_by_period" in res

    for cohort in res["cohorts"]:
        assert cohort["cohort_size"] > 0
        assert len(cohort["retention_periods"]) == 12
        for period in cohort["retention_periods"]:
            assert 0.0 <= period["retention_pct"] <= 100.0


# ── 3. Predictive CLV Tests ──────────────────────────────────────────────────

def test_predictive_clv_separation_and_bayesian_shrinkage(db_session):
    """Verifies strict separation of historical spend from 12M forward value and Bayesian shrinkage."""
    _seed_stage5_test_data(db_session)
    res = compute_predictive_clv(db_session, horizon_months=12)

    assert res["total_customers"] == 10
    assert res["aggregate_historical_revenue"] > 0
    assert res["aggregate_predicted_12m_future_value"] > 0
    assert len(res["customers"]) == 10

    for c in res["customers"]:
        # Strict separation: historical spend vs forward spend
        assert c["historical_spend"] > 0
        assert c["predicted_future_spend_12m"] > 0
        assert round(c["total_predicted_clv"], 2) == round(c["historical_spend"] + c["predicted_future_spend_12m"], 2)
        # Uncertainty bounds: lower <= predicted <= upper
        assert c["clv_lower_bound"] <= c["total_predicted_clv"] <= c["clv_upper_bound"]
        # Loyalty tier assignment
        assert c["clv_tier"] in ("Tier 1: Platinum", "Tier 2: Gold", "Tier 3: Silver", "Tier 4: Bronze")


def test_single_customer_clv_pathway(db_session):
    """Verifies single customer CLV retrieval and strategic recommendation pathway."""
    _seed_stage5_test_data(db_session)
    res = get_single_customer_clv(db_session, customer_id=1)
    assert res is not None
    assert res["customer_id"] == 1
    assert "uncertainty_bounds" in res
    assert len(res["recommendation_pathway"]) > 5

    missing = get_single_customer_clv(db_session, customer_id=999)
    assert missing is None


# ── 4. Catalog Normalizer Tests ──────────────────────────────────────────────

def test_catalog_normalizer_unit_and_brand_extraction():
    """Unit test for measurement extraction and category mapping."""
    meas1 = extract_unit_and_measurement("Studio Wireless Headphones (1.2 kg)")
    assert meas1["has_measurement"] is True
    assert meas1["normalized_value"] == 1.2
    assert meas1["normalized_unit"] == "kg"

    meas2 = extract_unit_and_measurement("Ultra 27-inch Display Monitor")
    assert meas2["has_measurement"] is True
    assert meas2["normalized_value"] == 27.0
    assert meas2["normalized_unit"] == "inches"

    subcat, parent = normalize_category("Headphones")
    assert parent == "Electronics"
    assert "Audio" in subcat or "Headphones" in subcat


def test_catalog_normalizer_database_audit_and_duplicates(db_session):
    """Verifies catalog normalization, quality scoring, near-duplicate detection, and non-destructive guarantee."""
    _seed_stage5_test_data(db_session)
    res = normalize_catalog(db_session)

    assert res["total_products_inspected"] == 3
    assert res["categories_normalized_count"] == 3
    assert res["units_extracted_count"] >= 2
    assert res["duplicate_candidates_found"] >= 1  # Product 1 and Product 3 are near-duplicates
    assert res["average_attribute_quality_score"] > 50.0

    # Non-destructive check: DB product records remain completely unchanged
    p1_db = db_session.query(Product).filter(Product.id == 1).first()
    assert p1_db.name == "Studio Wireless Headphones (1.2 kg)"
    assert p1_db.category == "Headphones"


# ── 5. Hybrid Recommendation Engine Tests ─────────────────────────────────────

def test_hybrid_recommender_scoring_and_stock_guard(db_session):
    """Verifies hybrid score calculation, alpha weighting, and verified in-stock filtering."""
    _seed_stage5_test_data(db_session)

    # c1 hybrid recommendations with alpha=0.6
    res = get_hybrid_recommendations(db_session, customer_id=1, top_n=5, alpha=0.6)
    assert res["customer_id"] == 1
    assert res["recommendation_count"] > 0

    recs = res["recommendations"]
    rec_pids = [r["product_id"] for r in recs]

    # Product 3 has current_stock=0 (out of stock) -> must be excluded by stock guard
    assert 3 not in rec_pids

    # Available products (Product 1 and 2)
    for rec in recs:
        assert rec["product_id"] in (1, 2)
        assert 0.0 <= rec["score"] <= 1.0
        assert rec["recommendation_type"] in ("HYBRID", "COLLABORATIVE", "POPULARITY_FALLBACK")
        assert len(rec["rationale"]) > 5


def test_hybrid_recommender_chronological_evaluation(db_session):
    """Verifies offline chronological evaluation comparing Hybrid vs pure CF vs Popularity."""
    _seed_stage5_test_data(db_session)
    res = evaluate_hybrid_engine(db_session, k=2, holdout_date="2024-10-01")

    assert "hit_rate_at_k" in res
    assert "mean_precision_at_k" in res
    assert "mean_recall_at_k" in res
    assert "model_comparisons" in res
    assert "Hybrid (CF + Content)" in res["model_comparisons"]
    assert "Pure Collaborative Filtering" in res["model_comparisons"]
    assert "Popularity Baseline" in res["model_comparisons"]


# ── 6. Conversion Funnel Tests ────────────────────────────────────────────────

def test_conversion_funnel_stages_and_dropoff(db_session):
    """Verifies 3 empirical funnel stages (View -> Cart -> Purchase) and authenticity note."""
    _seed_stage5_test_data(db_session)
    res = compute_conversion_funnel(db_session)

    assert "3-Stage" in res["funnel_name"]
    assert len(res["stages"]) == 3

    stages = res["stages"]
    assert stages[0]["event_type"] == "view"
    assert stages[1]["event_type"] == "add_to_cart"
    assert stages[2]["event_type"] == "purchase"

    for st in stages:
        assert st["total_events"] >= 0
        assert 0.0 <= st["overall_conversion_pct"] <= 100.0

    assert "synthetic data fabrication" in res["data_authenticity_declaration"]


# ── 7. Offer Strategy & Stock Impact Tests ────────────────────────────────────

def test_offer_strategy_segment_mapping(db_session):
    """Verifies personalized offer generation mapped to customer segments and churn risk."""
    _seed_stage5_test_data(db_session)
    res = generate_personalized_offer_strategy(db_session, limit=5)

    assert res["total_personalized_offers"] > 0
    assert "offers" in res
    for offer in res["offers"]:
        assert offer["target_segment"] in ("Champions / VIP", "At-Risk Churn", "Core Regulars")
        assert offer["discount_pct"] in (5.0, 10.0, 15.0)
        assert offer["discounted_price"] < offer["original_price"]
        assert len(offer["strategic_objective"]) > 0


def test_shared_ml_context_parity_matches_direct_calls(db_session):
    """Verify DEF-UAT-02 shared precomputed context yields exact mathematical parity."""
    _seed_stage5_test_data(db_session)
    churn_res = train_and_evaluate_churn_model(db_session)
    clv_direct = compute_predictive_clv(db_session)
    clv_shared = compute_predictive_clv(db_session, precomputed_churn=churn_res)
    assert clv_direct["aggregate_predicted_12m_future_value"] == clv_shared["aggregate_predicted_12m_future_value"]
    assert clv_direct["customers"] == clv_shared["customers"]

    ctx = _prepare_hybrid_context(db_session)
    rec_direct = get_hybrid_recommendations(db_session, customer_id=1, top_n=3, alpha=0.65)
    rec_shared = get_hybrid_recommendations(db_session, customer_id=1, top_n=3, alpha=0.65, prepared=ctx)
    assert rec_direct["recommendations"] == rec_shared["recommendations"]


def test_price_elasticity_hierarchy(db_session):
    """Verifies 3-tier price elasticity hierarchy and fallback with explicit disclosure."""
    _seed_stage5_test_data(db_session)
    p = db_session.query(Product).filter(Product.id == 1).first()

    res = resolve_price_elasticity(db_session, p)
    assert res["elasticity"] > 0.0
    # Vendor has < 30 price variations -> resolves to Category Benchmark or Platform Fallback
    assert res["source"] in ("CATEGORY_BENCHMARK", "PLATFORM_FALLBACK")
    assert res["is_empirically_learned"] is False


def test_stock_impact_safety_approved_and_suppressed(db_session):
    """
    Verifies the stock impact safety formula:
      Ending Stock = Current Stock + Replenishment - Baseline Demand - Lift.
      If Ending Stock >= Safety Stock => APPROVED.
      If Ending Stock < Safety Stock => SUPPRESSED.
    """
    _seed_stage5_test_data(db_session)

    # Product 1: Current Stock = 40, Safety Stock = 15
    # Moderate discount: Ending Stock remains >= 15 -> APPROVED
    res_approved = evaluate_stock_impact_safety(
        db_session,
        product_id=1,
        discount_pct=5.0,
        horizon_days=14,
        confirmed_replenishment=0,
    )
    assert res_approved["status"] == "APPROVED"
    assert res_approved["projected_ending_stock"] >= res_approved["safety_stock"]
    assert "satisfies or exceeds safety stock threshold" in res_approved["decision_reason"]

    # Product 2: Current Stock = 12, Safety Stock = 10
    # When tested with baseline demand over 60 days + promotional lift,
    # Ending stock drops below 10 -> SUPPRESSED
    # Baseline demand = (7 total sold / 365) * 60 = 1.15 -> round = 1.2
    # Discount 30% * 1.4 elasticity = 0.504 lift -> total demand = 1.7
    # Ending stock = 12 - 1.7 = 10.3. Let's use horizon_days=90 or discount=40% or adjust stock to 10
    # With horizon_days=90: baseline = (7/365)*90 = 1.7, lift = 1.7*1.4*0.4 = 0.95, total demand = 2.65
    # Ending stock = 12 - 2.65 = 9.35 < 10 (safety stock) -> SUPPRESSED!
    res_suppressed = evaluate_stock_impact_safety(
        db_session,
        product_id=2,
        discount_pct=40.0,
        horizon_days=90,
        confirmed_replenishment=0,
    )
    assert res_suppressed["status"] == "SUPPRESSED"
    assert res_suppressed["projected_ending_stock"] < res_suppressed["safety_stock"]
    assert "falls below safety stock" in res_suppressed["decision_reason"]


# ── 8. FastAPI Client Route Integration Tests ─────────────────────────────────

def test_api_routes_stage5_integration(client, db_session):
    """Verifies all Stage 5 REST API routes via FastAPI testclient."""
    _seed_stage5_test_data(db_session)

    # Customer endpoints
    r_churn = client.get("/analytics/customers/churn")
    assert r_churn.status_code == 200
    assert "metrics" in r_churn.json()

    r_single_churn = client.get("/analytics/customers/churn/1")
    assert r_single_churn.status_code == 200
    assert r_single_churn.json()["customer_id"] == 1

    r_churn_404 = client.get("/analytics/customers/churn/999")
    assert r_churn_404.status_code == 404

    r_cohorts = client.get("/analytics/customers/cohorts")
    assert r_cohorts.status_code == 200
    assert "cohorts" in r_cohorts.json()

    r_clv = client.get("/analytics/customers/clv")
    assert r_clv.status_code == 200
    assert "customers" in r_clv.json()

    r_single_clv = client.get("/analytics/customers/clv/1")
    assert r_single_clv.status_code == 200
    assert r_single_clv.json()["customer_id"] == 1

    r_clv_404 = client.get("/analytics/customers/clv/999")
    assert r_clv_404.status_code == 404

    r_funnel = client.get("/analytics/customers/conversion-funnel")
    assert r_funnel.status_code == 200
    assert len(r_funnel.json()["stages"]) == 3

    # Catalog endpoints
    r_catalog = client.get("/catalog/normalize")
    assert r_catalog.status_code == 200
    assert r_catalog.json()["total_products_inspected"] == 3

    r_single_cat = client.get("/catalog/normalize/1")
    assert r_single_cat.status_code == 200
    assert r_single_cat.json()["product_id"] == 1

    r_cat_404 = client.get("/catalog/normalize/999")
    assert r_cat_404.status_code == 404

    # Recommendation endpoints
    r_rec_hybrid = client.get("/recommendations/hybrid/1?alpha=0.6")
    assert r_rec_hybrid.status_code == 200
    assert r_rec_hybrid.json()["customer_id"] == 1

    r_rec_eval = client.get("/recommendations/hybrid/evaluation?k=2")
    assert r_rec_eval.status_code == 200
    assert "hit_rate_at_k" in r_rec_eval.json()

    # Offer & Stock Impact endpoints
    r_strat = client.get("/offers/strategy?limit=5")
    assert r_strat.status_code == 200
    assert "offers" in r_strat.json()

    r_elast = client.get("/offers/elasticity/1")
    assert r_elast.status_code == 200
    assert "elasticity" in r_elast.json()

    r_sim_post = client.post("/offers/stock-impact", json={
        "product_id": 1,
        "discount_pct": 10.0,
        "forecast_horizon_days": 14,
        "confirmed_replenishment": 0,
    })
    assert r_sim_post.status_code == 200
    assert r_sim_post.json()["status"] in ("APPROVED", "SUPPRESSED")

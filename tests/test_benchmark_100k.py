"""
tests/test_benchmark_100k.py — Test Suite for ShopSense Milestone 4 Phase 1 (100K Benchmark).

Verifies:
  1. Isolated benchmark paths prevent overwriting operational `data/*.csv` files.
  2. Generation of 100,000+ realistic synthetic transactions matches ShopSense ORM & ETL schema rules.
  3. Determinism / reproducibility with a fixed random seed.
  4. Vectorized analytics accuracy & mathematical invariants (and exact parity with `revenue_service`).
  5. End-to-end telemetry capture (timings, DataFrame RAM, tracemalloc, process RSS, Markdown report).
"""

import hashlib
import os
import pytest
import pandas as pd

from app.models.vendor import Vendor
from app.models.product import Product
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.services import revenue_service
from app.services.etl.validation import validate_row
from benchmarks.dataset_generator import (
    DEFAULT_NUM_RECORDS,
    generate_reference_dimensions,
    generate_benchmark_transactions,
    generate_and_save_benchmark_dataset,
    resolve_benchmark_paths,
    validate_benchmark_dataframe,
)
from benchmarks.analytics_engine import (
    compute_total_revenue_and_gmv,
    compute_average_transaction_value,
    compute_vendor_analytics,
    run_all_benchmark_analytics,
)
from benchmarks.run_100k_benchmark import run_benchmark


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_01_isolated_paths_and_existing_data_preservation(tmp_path):
    """Benchmark runner refuses data/ root and never modifies existing data/*.csv files."""
    with pytest.raises(ValueError, match="isolated subdirectory"):
        resolve_benchmark_paths(os.path.join(os.getcwd(), "data"))

    existing_files = [
        os.path.join("data", "transactions.csv"),
        os.path.join("data", "vendors.csv"),
        os.path.join("data", "products.csv"),
        os.path.join("data", "customers.csv"),
    ]
    before_hashes = {p: _sha256(p) for p in existing_files if os.path.exists(p)}

    out_dir = str(tmp_path / "isolated_bench")
    info = generate_and_save_benchmark_dataset(n_records=100_000, seed=42, output_dir=out_dir)

    assert info["record_count"] == 100_000
    assert os.path.exists(info["paths"].transactions_csv)
    for p, digest in before_hashes.items():
        assert _sha256(p) == digest


def test_02_100k_schema_validity_and_etl_compatibility():
    """Verify all 100,000 generated records honor ShopSense schema constraints & ETL validate_row."""
    vendors_df, products_df, customers_df = generate_reference_dimensions(seed=42)
    tx_df = generate_benchmark_transactions(
        n_records=DEFAULT_NUM_RECORDS,
        seed=42,
        vendors_df=vendors_df,
        products_df=products_df,
        customers_df=customers_df,
    )
    assert len(tx_df) == 100_000

    val_summary = validate_benchmark_dataframe(tx_df, vendors_df, products_df, customers_df)
    assert val_summary["all_valid"] is True
    assert all(val_summary["checks"].values())

    # Cross-check sample slice directly against app.services.etl.validation.validate_row
    valid_pids = set(products_df["product_id"].tolist())
    valid_vids = set(vendors_df["vendor_id"].tolist())
    valid_cids = set(customers_df["customer_id"].tolist())
    pv_map = dict(zip(products_df["product_id"], products_df["vendor_id"]))

    sample_rows = tx_df.iloc[[0, 1000, 25000, 50000, 99999]].to_dict(orient="records")
    for idx, row in enumerate(sample_rows, start=1):
        row["_row_number"] = idx
        row["transaction_date"] = row["transaction_date"].to_pydatetime()
        vr = validate_row(
            row=row,
            valid_product_ids=valid_pids,
            valid_vendor_ids=valid_vids,
            valid_customer_ids=valid_cids,
            product_vendor_map=pv_map,
        )
        assert vr.is_valid is True, f"ETL validate_row rejected sample row {idx}: {vr.errors}"


def test_03_fixed_seed_reproducibility():
    """Two runs with the same fixed seed yield identical DataFrames; different seed differs."""
    tx_a = generate_benchmark_transactions(n_records=100_000, seed=42)
    tx_b = generate_benchmark_transactions(n_records=100_000, seed=42)
    tx_c = generate_benchmark_transactions(n_records=100_000, seed=99)

    pd.testing.assert_frame_equal(tx_a, tx_b)
    assert not tx_a["product_id"].equals(tx_c["product_id"])


def test_04_vectorized_analytics_invariants_and_service_parity(db_session):
    """
    Validate mathematical consistency on 100K records and exact parity with
    ShopSense's `app.services.revenue_service` functions on an isolated test slice.
    """
    vendors_df, products_df, customers_df = generate_reference_dimensions(seed=42)
    tx_df = generate_benchmark_transactions(
        n_records=100_000,
        seed=42,
        vendors_df=vendors_df,
        products_df=products_df,
        customers_df=customers_df,
    )

    out = run_all_benchmark_analytics(tx_df, vendors_df, products_df, customers_df)
    res = out["results"]

    gmv = res["total_revenue_and_gmv"]["gross_merchandise_value"]
    net = res["total_revenue_and_gmv"]["net_sales"]
    aov = res["average_transaction_value"]["avg_order_value"]
    assert res["total_revenue_and_gmv"]["total_transactions"] == 100_000
    assert gmv > net > 0
    assert aov == round(gmv / 100_000, 2)

    vend_res = res["vendor_sales_and_ranking"]
    assert 99.9 <= vend_res["market_share_sum_pct"] <= 100.1
    assert vend_res["top_vendor"]["rank"] == 1

    cat_sum = round(sum(c["revenue"] for c in res["category_and_payment_breakdown"]["categories"]), 2)
    assert abs(cat_sum - gmv) < 0.1

    mart_res = res["daily_sales_mart_rollup"]
    assert abs(mart_res["mart_gross_gmv"] - gmv) < 0.1
    assert mart_res["mart_total_units"] == res["total_revenue_and_gmv"]["total_units_sold"]

    # Parity test on 200-row slice inserted strictly into ephemeral pytest SQLite db_session
    slice_tx = tx_df.head(200).copy()
    used_vids = sorted(slice_tx["vendor_id"].unique().tolist())
    used_pids = sorted(slice_tx["product_id"].unique().tolist())
    used_cids = sorted(slice_tx["customer_id"].unique().tolist())

    for _, vr in vendors_df[vendors_df["vendor_id"].isin(used_vids)].iterrows():
        db_session.add(Vendor(
            id=int(vr["vendor_id"]),
            name=str(vr["vendor_name"]),
            email=f"v{int(vr['vendor_id'])}@bench.test",
            phone="9999999999",
            status="ACTIVE",
            commission_tier=str(vr["commission_tier"]),
            commission_rate=float(vr["commission_rate"]),
        ))
    db_session.flush()

    for _, pr in products_df[products_df["product_id"].isin(used_pids)].iterrows():
        db_session.add(Product(
            id=int(pr["product_id"]),
            name=str(pr["product_name"]),
            price=float(pr["price"]),
            cost_price=float(pr["cost_price"]),
            category=str(pr["category"]),
            parent_category=str(pr["parent_category"]),
            vendor_id=int(pr["vendor_id"]),
        ))
    for _, cr in customers_df[customers_df["customer_id"].isin(used_cids)].iterrows():
        db_session.add(Customer(
            customer_id=int(cr["customer_id"]),
            name=f"Cust {int(cr['customer_id'])}",
            email=f"c{int(cr['customer_id'])}@bench.test",
            city=str(cr["city"]),
            region=str(cr["region"]),
        ))
    db_session.flush()

    for _, tr in slice_tx.iterrows():
        db_session.add(Transaction(
            transaction_id=int(tr["transaction_id"]),
            product_id=int(tr["product_id"]),
            vendor_id=int(tr["vendor_id"]),
            customer_id=int(tr["customer_id"]),
            quantity=int(tr["quantity"]),
            unit_price=float(tr["unit_price"]),
            amount=float(tr["amount"]),
            discount_amount=float(tr["discount_amount"]),
            payment_method=str(tr["payment_method"]),
            payment_status=str(tr["payment_status"]),
            effective_commission_rate=float(tr["effective_commission_rate"]),
            source_system=str(tr["source_system"]),
            source_transaction_id=str(tr["source_transaction_id"]),
            transaction_date=tr["transaction_date"].to_pydatetime(),
        ))
    db_session.commit()

    vec_rev = compute_total_revenue_and_gmv(slice_tx)
    vec_aov = compute_average_transaction_value(slice_tx)
    vec_vend = compute_vendor_analytics(slice_tx, vendors_df)

    assert revenue_service.calculate_gmv(db_session) == vec_rev["gross_merchandise_value"]
    assert revenue_service.avg_order_value(db_session) == vec_aov["avg_order_value"]
    db_bench = revenue_service.get_vendor_benchmarking(db_session)
    assert db_bench["total_gmv"] == vec_rev["gross_merchandise_value"]
    assert db_bench["benchmarks"][0]["vendor_id"] == vec_vend["top_vendor"]["vendor_id"]


def test_05_end_to_end_100k_benchmark_runner_and_report(tmp_path):
    """Run complete 100K benchmark end-to-end and verify real timings, memory & report generation."""
    bench_dir = str(tmp_path / "bench_data")
    report_file = str(tmp_path / "benchmark_100k_report.md")

    summary = run_benchmark(
        n_records=100_000,
        seed=42,
        output_dir=bench_dir,
        report_path=report_file,
    )

    assert summary["record_count"] == 100_000
    assert summary["validation"]["all_valid"] is True
    assert summary["generation"]["generation_time_s"] > 0
    assert summary["loading"]["load_time_s"] > 0
    assert summary["analytics"]["total_analytics_time_s"] > 0
    assert len(summary["analytics"]["timings"]) == 8
    assert summary["memory"]["transactions_df_memory_mb"] > 0
    assert summary["memory"]["tracemalloc_peak_mb"] > 0
    assert summary["memory"]["rss_after_mb"] > 0
    assert summary["environment"]["pandas_version"]

    assert os.path.exists(report_file)
    content = open(report_file, encoding="utf-8").read()
    assert "100,000" in content
    assert "Gross Merchandise Value" in content
    assert "Bottlenecks" in content

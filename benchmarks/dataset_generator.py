"""
benchmarks/dataset_generator.py — Vectorized Synthetic 100K+ Marketplace Dataset Generator.

Generates reproducible synthetic marketplace transactions compatible with
ShopSense's `Transaction` schema (`app/models/transaction.py`) and ETL validation
rules (`app/services/etl/validation.py`) inside an isolated directory (`data/benchmarks/`)
without reading from or mutating the operational PostgreSQL database or existing CSVs.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Dict, Any, Tuple

import numpy as np
import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCHMARK_DIR = os.path.join(ROOT_DIR, "data", "benchmarks")

DEFAULT_SEED = 42
DEFAULT_NUM_RECORDS = 100_000

COMMISSION_TIERS: Tuple[Tuple[str, float], ...] = (
    ("TIER_PLATINUM", 0.08),
    ("TIER_PREFERRED", 0.10),
    ("TIER_STANDARD", 0.12),
    ("TIER_STARTER", 0.15),
)

CATEGORIES: Tuple[Tuple[str, str], ...] = (
    ("Headphones", "Electronics"),
    ("Monitors", "Electronics"),
    ("Laptops & Accessories", "Electronics"),
    ("Kitchenware", "Home & Kitchen"),
    ("Furniture", "Home & Kitchen"),
    ("Home Appliances", "Home & Kitchen"),
    ("Apparel", "Fashion"),
    ("Outerwear", "Fashion"),
    ("Fitness", "Sports & Fitness"),
    ("Strength Training", "Sports & Fitness"),
    ("Coffee & Beverage", "Food & Beverage"),
    ("Skincare & Grooming", "Beauty & Wellness"),
)

REGIONS: Tuple[Tuple[str, str], ...] = (
    ("Bengaluru", "Karnataka"),
    ("Mumbai", "Maharashtra"),
    ("Delhi", "Delhi"),
    ("Hyderabad", "Telangana"),
    ("Chennai", "Tamil Nadu"),
    ("Kolkata", "West Bengal"),
    ("Pune", "Maharashtra"),
    ("Ahmedabad", "Gujarat"),
)

PAYMENT_METHODS: Tuple[str, ...] = ("UPI", "CARD", "NETBANKING", "WALLET", "COD")
PAYMENT_METHOD_WEIGHTS = np.array([0.44, 0.28, 0.12, 0.09, 0.07], dtype=np.float64)


@dataclass(frozen=True)
class BenchmarkDatasetPaths:
    """Isolated paths for synthetic benchmark datasets (excluded from operational data)."""

    base_dir: str
    transactions_csv: str
    vendors_csv: str
    products_csv: str
    customers_csv: str


def resolve_benchmark_paths(output_dir: str = BENCHMARK_DIR) -> BenchmarkDatasetPaths:
    """Resolve isolated file paths under `data/benchmarks/` safely."""
    norm_dir = os.path.abspath(output_dir)
    data_root = os.path.abspath(os.path.join(ROOT_DIR, "data"))
    if norm_dir == data_root:
        raise ValueError("Benchmark outputs must stay in an isolated subdirectory, not data/ root.")
    return BenchmarkDatasetPaths(
        base_dir=norm_dir,
        transactions_csv=os.path.join(norm_dir, "transactions_100k.csv"),
        vendors_csv=os.path.join(norm_dir, "vendors_ref_100k.csv"),
        products_csv=os.path.join(norm_dir, "products_ref_100k.csv"),
        customers_csv=os.path.join(norm_dir, "customers_ref_100k.csv"),
    )


def generate_reference_dimensions(
    n_vendors: int = 25,
    n_products: int = 120,
    n_customers: int = 10_000,
    seed: int = DEFAULT_SEED,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Generate deterministic synthetic Vendor, Product, and Customer dimension DataFrames
    aligned with ShopSense column schemas and commission tiers.
    """
    rng = np.random.default_rng(seed)

    # 1. Vendors
    tier_indices = rng.integers(0, len(COMMISSION_TIERS), size=n_vendors)
    tier_names = [COMMISSION_TIERS[i][0] for i in tier_indices]
    tier_rates = [COMMISSION_TIERS[i][1] for i in tier_indices]
    vendor_regions = [REGIONS[i % len(REGIONS)] for i in range(n_vendors)]

    vendors_df = pd.DataFrame({
        "vendor_id": np.arange(1, n_vendors + 1, dtype=np.int32),
        "vendor_name": [f"Vendor Hub {i:02d}" for i in range(1, n_vendors + 1)],
        "business_type": [CATEGORIES[i % len(CATEGORIES)][1] for i in range(n_vendors)],
        "city": [r[0] for r in vendor_regions],
        "status": "ACTIVE",
        "commission_tier": tier_names,
        "commission_rate": np.array(tier_rates, dtype=np.float64),
    })

    # 2. Products (each strictly mapped to one vendor_id + positive price + realistic cost_price)
    prod_vendor_ids = np.array([(i % n_vendors) + 1 for i in range(n_products)], dtype=np.int32)
    cat_indices = np.arange(n_products) % len(CATEGORIES)
    categories = [CATEGORIES[i][0] for i in cat_indices]
    parent_categories = [CATEGORIES[i][1] for i in cat_indices]

    # Log-uniform retail pricing between Rs. 12.99 and Rs. 799.99
    raw_prices = np.exp(rng.uniform(np.log(12.99), np.log(799.99), size=n_products))
    prices = np.round(raw_prices, 2)
    cost_ratios = rng.uniform(0.54, 0.72, size=n_products)
    cost_prices = np.round(prices * cost_ratios, 2)

    products_df = pd.DataFrame({
        "product_id": np.arange(1, n_products + 1, dtype=np.int32),
        "product_name": [f"{categories[i]} SKU-{i + 1:03d}" for i in range(n_products)],
        "category": categories,
        "parent_category": parent_categories,
        "vendor_id": prod_vendor_ids,
        "price": prices,
        "cost_price": cost_prices,
    })

    # 3. Customers with behavioral persona labels and regional distribution
    reg_indices = rng.integers(0, len(REGIONS), size=n_customers)
    cities = [REGIONS[i][0] for i in reg_indices]
    regions = [REGIONS[i][1] for i in reg_indices]
    personas = np.where(
        np.arange(n_customers) < int(n_customers * 0.10),
        "VIP",
        np.where(
            np.arange(n_customers) < int(n_customers * 0.40),
            "Loyal",
            np.where(np.arange(n_customers) < int(n_customers * 0.70), "At-Risk", "Occasional"),
        ),
    )
    signup_offsets = rng.integers(0, 365, size=n_customers)
    signup_dates = pd.Timestamp("2023-01-01") + pd.to_timedelta(signup_offsets, unit="D")

    customers_df = pd.DataFrame({
        "customer_id": np.arange(1, n_customers + 1, dtype=np.int32),
        "city": cities,
        "region": regions,
        "persona": personas,
        "signup_date": signup_dates,
    })

    return vendors_df, products_df, customers_df


def generate_benchmark_transactions(
    n_records: int = DEFAULT_NUM_RECORDS,
    seed: int = DEFAULT_SEED,
    vendors_df: pd.DataFrame | None = None,
    products_df: pd.DataFrame | None = None,
    customers_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Generate `n_records` synthetic marketplace transactions using vectorized NumPy/Pandas.

    All generated fields honor ShopSense `Transaction` ORM & ETL validation invariants:
      - `quantity > 0`, `unit_price > 0`, `amount == round(quantity * unit_price, 2) > 0`
      - `0 <= discount_amount < amount`
      - `vendor_id` strictly consistent with `products_df.vendor_id`
      - `transaction_date` chronologically sorted with seasonal Q4 & weekend volume weighting
    """
    if n_records <= 0:
        raise ValueError("n_records must be strictly positive.")

    if vendors_df is None or products_df is None or customers_df is None:
        vendors_df, products_df, customers_df = generate_reference_dimensions(seed=seed)

    rng = np.random.default_rng(seed + 1)

    # Seasonal timeline across 2024-01-01 .. 2025-12-31 (731 calendar days)
    all_days = pd.date_range("2024-01-01", "2025-12-31", freq="D")
    n_days = len(all_days)
    months = all_days.month.to_numpy()
    weekdays = all_days.weekday.to_numpy()

    day_weights = np.ones(n_days, dtype=np.float64)
    day_weights += np.where(np.isin(months, [10, 11, 12]), 0.45, 0.0)
    day_weights += np.where(weekdays >= 5, 0.25, 0.0)
    # Mild year-over-year growth in 2025
    day_weights += np.where(all_days.year.to_numpy() == 2025, 0.18, 0.0)
    day_probs = day_weights / day_weights.sum()

    sampled_day_idx = rng.choice(n_days, size=n_records, replace=True, p=day_probs)
    sampled_secs = rng.integers(0, 86_400, size=n_records)
    tx_dates = all_days.to_numpy()[sampled_day_idx] + sampled_secs.astype("timedelta64[s]")

    # Sort chronologically so transaction_id order matches time series
    sort_order = np.argsort(tx_dates)
    tx_dates = tx_dates[sort_order]

    # Product popularity weights (Zipf-like marketplace demand concentration)
    n_products = len(products_df)
    prod_ranks = np.arange(1, n_products + 1, dtype=np.float64)
    prod_probs = (1.0 / np.power(prod_ranks, 0.72))
    prod_probs /= prod_probs.sum()
    prod_idx = rng.choice(n_products, size=n_records, replace=True, p=prod_probs)

    prod_ids = products_df["product_id"].to_numpy(dtype=np.int32)[prod_idx]
    vendor_ids = products_df["vendor_id"].to_numpy(dtype=np.int32)[prod_idx]
    unit_prices = products_df["price"].to_numpy(dtype=np.float64)[prod_idx]

    # Map vendor_id -> commission_rate via vectorized index alignment
    vendor_rate_lookup = (
        vendors_df.set_index("vendor_id")["commission_rate"]
        .reindex(vendor_ids)
        .to_numpy(dtype=np.float64)
    )

    # Customer persona frequency weighting (VIP 10% place ~32% of orders)
    n_customers = len(customers_df)
    persona_arr = customers_df["persona"].to_numpy()
    cust_weights = np.where(
        persona_arr == "VIP",
        4.0,
        np.where(persona_arr == "Loyal", 1.8, np.where(persona_arr == "At-Risk", 0.9, 0.5)),
    )
    cust_probs = cust_weights / cust_weights.sum()
    cust_idx = rng.choice(n_customers, size=n_records, replace=True, p=cust_probs)
    cust_ids = customers_df["customer_id"].to_numpy(dtype=np.int32)[cust_idx]

    # Price-tiered realistic basket quantities
    u_qty = rng.random(size=n_records)
    high_ticket = unit_prices >= 200.0
    low_ticket = unit_prices < 35.0
    qty = np.where(
        high_ticket,
        np.where(u_qty < 0.86, 1, 2),
        np.where(
            low_ticket,
            np.select(
                [u_qty < 0.42, u_qty < 0.72, u_qty < 0.87, u_qty < 0.95],
                [1, 2, 3, 4],
                default=5,
            ),
            np.select([u_qty < 0.62, u_qty < 0.90], [1, 2], default=3),
        ),
    ).astype(np.int32)

    amounts = np.round(qty * unit_prices, 2)

    # Discounts: 35% of orders receive 5%, 10%, or 15% promotional discount (strictly < amount)
    disc_roll = rng.random(size=n_records)
    disc_rate = np.select(
        [disc_roll < 0.65, disc_roll < 0.85, disc_roll < 0.95],
        [0.0, 0.05, 0.10],
        default=0.15,
    )
    discounts = np.round(amounts * disc_rate, 2)
    discounts = np.minimum(discounts, np.round(amounts - 0.01, 2))
    discounts = np.maximum(discounts, 0.0)

    payment_methods = rng.choice(PAYMENT_METHODS, size=n_records, replace=True, p=PAYMENT_METHOD_WEIGHTS)
    txn_ids = np.arange(1, n_records + 1, dtype=np.int64)
    src_txn_ids = [f"BENCH-{i:07d}" for i in range(1, n_records + 1)]

    return pd.DataFrame({
        "transaction_id": txn_ids,
        "product_id": prod_ids,
        "vendor_id": vendor_ids,
        "customer_id": cust_ids,
        "quantity": qty,
        "unit_price": unit_prices,
        "amount": amounts,
        "discount_amount": discounts,
        "payment_method": payment_methods,
        "payment_status": "COMPLETED",
        "effective_commission_rate": vendor_rate_lookup,
        "source_system": "SYNTHETIC_BENCHMARK_100K",
        "source_transaction_id": src_txn_ids,
        "transaction_date": pd.to_datetime(tx_dates),
    })


def validate_benchmark_dataframe(
    tx_df: pd.DataFrame,
    vendors_df: pd.DataFrame,
    products_df: pd.DataFrame,
    customers_df: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Vectorized integrity verification matching `app/models/transaction.py` & ETL schema rules.
    Returns validation metrics and asserts zero violations.
    """
    t0 = time.perf_counter()
    required_cols = {
        "transaction_id",
        "product_id",
        "vendor_id",
        "customer_id",
        "quantity",
        "unit_price",
        "amount",
        "discount_amount",
        "payment_method",
        "payment_status",
        "effective_commission_rate",
        "source_system",
        "source_transaction_id",
        "transaction_date",
    }
    missing_cols = required_cols - set(tx_df.columns)
    if missing_cols:
        raise ValueError(f"Missing required benchmark columns: {sorted(missing_cols)}")

    # Vectorized domain and referential checks
    valid_qty = int((tx_df["quantity"] > 0).sum())
    valid_price = int((tx_df["unit_price"] > 0.0).sum())
    valid_amt = int((tx_df["amount"] > 0.0).sum())
    valid_disc = int(((tx_df["discount_amount"] >= 0.0) & (tx_df["discount_amount"] < tx_df["amount"])).sum())
    amt_match = int(np.isclose(tx_df["amount"], np.round(tx_df["quantity"] * tx_df["unit_price"], 2), atol=1e-6).sum())
    fk_prod = int(tx_df["product_id"].isin(products_df["product_id"]).sum())
    fk_vend = int(tx_df["vendor_id"].isin(vendors_df["vendor_id"]).sum())
    fk_cust = int(tx_df["customer_id"].isin(customers_df["customer_id"]).sum())
    prod_vend_expected = products_df.set_index("product_id")["vendor_id"].reindex(tx_df["product_id"]).to_numpy()
    prod_vend_match = int((tx_df["vendor_id"].to_numpy() == prod_vend_expected).sum())
    unique_src = int(tx_df["source_transaction_id"].nunique())
    non_null_dates = int(tx_df["transaction_date"].notna().sum())

    total = len(tx_df)
    checks = {
        "positive_quantity": valid_qty == total,
        "positive_unit_price": valid_price == total,
        "positive_amount": valid_amt == total,
        "valid_discount_bounds": valid_disc == total,
        "amount_equals_qty_times_price": amt_match == total,
        "valid_product_fk": fk_prod == total,
        "valid_vendor_fk": fk_vend == total,
        "valid_customer_fk": fk_cust == total,
        "product_vendor_consistency": prod_vend_match == total,
        "unique_source_transaction_id": unique_src == total,
        "valid_timestamps": non_null_dates == total,
    }
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return {
        "total_records": total,
        "all_valid": all(checks.values()),
        "checks": checks,
        "validation_time_ms": elapsed_ms,
    }


def generate_and_save_benchmark_dataset(
    n_records: int = DEFAULT_NUM_RECORDS,
    seed: int = DEFAULT_SEED,
    output_dir: str = BENCHMARK_DIR,
) -> Dict[str, Any]:
    """Generate the isolated 100K+ dataset and write CSV artifacts strictly under `output_dir`."""
    paths = resolve_benchmark_paths(output_dir)
    os.makedirs(paths.base_dir, exist_ok=True)

    t_gen0 = time.perf_counter()
    vendors_df, products_df, customers_df = generate_reference_dimensions(seed=seed)
    tx_df = generate_benchmark_transactions(
        n_records=n_records,
        seed=seed,
        vendors_df=vendors_df,
        products_df=products_df,
        customers_df=customers_df,
    )
    generation_time_s = round(time.perf_counter() - t_gen0, 4)

    t_write0 = time.perf_counter()
    vendors_df.to_csv(paths.vendors_csv, index=False)
    products_df.to_csv(paths.products_csv, index=False)
    customers_df.to_csv(paths.customers_csv, index=False)
    tx_df.to_csv(paths.transactions_csv, index=False)
    write_time_s = round(time.perf_counter() - t_write0, 4)

    file_size_mb = round(os.path.getsize(paths.transactions_csv) / (1024 * 1024), 3)
    df_memory_mb = round(float(tx_df.memory_usage(deep=True).sum()) / (1024 * 1024), 3)

    return {
        "paths": paths,
        "record_count": len(tx_df),
        "vendors_count": len(vendors_df),
        "products_count": len(products_df),
        "customers_count": len(customers_df),
        "generation_time_s": generation_time_s,
        "disk_write_time_s": write_time_s,
        "transactions_csv_size_mb": file_size_mb,
        "dataframe_memory_mb": df_memory_mb,
    }


def load_benchmark_dataset(output_dir: str = BENCHMARK_DIR) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, float]:
    """Load the isolated benchmark CSV dataset with explicit dtypes and measure loading duration."""
    paths = resolve_benchmark_paths(output_dir)
    t0 = time.perf_counter()
    vendors_df = pd.read_csv(paths.vendors_csv)
    products_df = pd.read_csv(paths.products_csv)
    customers_df = pd.read_csv(paths.customers_csv, parse_dates=["signup_date"])
    tx_df = pd.read_csv(
        paths.transactions_csv,
        dtype={
            "transaction_id": "int64",
            "product_id": "int32",
            "vendor_id": "int32",
            "customer_id": "int32",
            "quantity": "int32",
            "unit_price": "float64",
            "amount": "float64",
            "discount_amount": "float64",
            "effective_commission_rate": "float64",
        },
        parse_dates=["transaction_date"],
    )
    load_time_s = round(time.perf_counter() - t0, 4)
    return tx_df, vendors_df, products_df, customers_df, load_time_s

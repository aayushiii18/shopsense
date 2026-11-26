"""ShopSense Milestone 4 Phase 1 — Isolated 100K Transaction Benchmark Package."""

from benchmarks.dataset_generator import (
    DEFAULT_SEED,
    DEFAULT_NUM_RECORDS,
    BENCHMARK_DIR,
    generate_reference_dimensions,
    generate_benchmark_transactions,
    generate_and_save_benchmark_dataset,
    load_benchmark_dataset,
    validate_benchmark_dataframe,
)
from benchmarks.analytics_engine import (
    compute_total_revenue_and_gmv,
    compute_average_transaction_value,
    compute_vendor_analytics,
    compute_product_analytics,
    compute_category_and_payment_analytics,
    compute_time_trends,
    compute_customer_rfm_analytics,
    compute_daily_sales_mart_aggregation,
    run_all_benchmark_analytics,
)

__all__ = [
    "DEFAULT_SEED",
    "DEFAULT_NUM_RECORDS",
    "BENCHMARK_DIR",
    "generate_reference_dimensions",
    "generate_benchmark_transactions",
    "generate_and_save_benchmark_dataset",
    "load_benchmark_dataset",
    "validate_benchmark_dataframe",
    "compute_total_revenue_and_gmv",
    "compute_average_transaction_value",
    "compute_vendor_analytics",
    "compute_product_analytics",
    "compute_category_and_payment_analytics",
    "compute_time_trends",
    "compute_customer_rfm_analytics",
    "compute_daily_sales_mart_aggregation",
    "run_all_benchmark_analytics",
]

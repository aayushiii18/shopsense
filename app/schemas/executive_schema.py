"""
app/schemas/executive_schema.py — Pydantic response schemas for Milestone 4 Phase 2 Executive Analytics API.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class DateRangeMetadata(BaseModel):
    """Applied date-range and optional vendor filter metadata."""

    start_date: Optional[str] = Field(None, description="Inclusive start date filter (YYYY-MM-DD) if applied")
    end_date: Optional[str] = Field(None, description="Inclusive end date filter (YYYY-MM-DD) if applied")
    is_filtered: bool = Field(False, description="True if a start_date or end_date filter was supplied")
    vendor_id: Optional[int] = Field(None, description="Vendor ID scope if filtered to a single vendor")


class ExecutiveFinancialKPIs(BaseModel):
    """Centralized executive financial & accounting metrics honoring strict COGS coverage rules."""

    gross_sales_gmv: float = Field(..., description="Total Gross Merchandise Value: sum(Transaction.amount)")
    discounts_total: float = Field(..., description="Total promotional discounts allocated across orders")
    refunds_total: float = Field(..., description="Total completed refunds deducted from gross sales")
    net_sales: float = Field(..., description="Net sales = max(0, gross_sales_gmv - discounts_total - refunds_total)")
    total_transactions: int = Field(..., description="Total number of transactions in scope")
    total_units_sold: int = Field(..., description="Total item units sold across transactions in scope")
    avg_order_value: float = Field(..., description="Average Order Value (GMV / total_transactions)")
    avg_net_order_value: float = Field(..., description="Average Net Order Value (net_sales / total_transactions)")
    has_cost_data: bool = Field(..., description="True when at least one transaction in scope has product cost_price")
    cost_coverage_complete: bool = Field(..., description="True when >= 99.9% of net sales have recorded cost_price")
    is_partial_profit: bool = Field(..., description="True when cost data exists for some, but not all, net sales")
    cogs_coverage_pct: float = Field(..., description="Percentage of Net Sales backed by verified product cost_price")
    covered_net_sales: float = Field(..., description="Net sales attributed to products with verified cost_price")
    covered_cogs: float = Field(..., description="Cost of Goods Sold across cost-covered transactions")
    gross_profit_reported: Optional[float] = Field(
        None,
        description="Reported gross profit on cost-covered items only; null when 0% cost data exists",
    )
    gross_margin_pct_reported: Optional[float] = Field(
        None,
        description="Reported gross margin % on cost-covered items only; null when 0% cost data exists",
    )
    coverage_status: str = Field(..., description="Explicit diagnostic note describing cost data completeness")


class PeriodComparisonMetrics(BaseModel):
    """Time-period comparison metrics computed when underlying comparative history exists."""

    comparison_supported: bool = Field(
        ..., description="True only when underlying comparative period transactions exist"
    )
    comparison_type: str = Field(
        ...,
        description="'window_over_previous_window', 'latest_month_vs_previous_month', or 'insufficient_data'",
    )
    current_period_label: Optional[str] = Field(None, description="Label describing the current evaluated window")
    previous_period_label: Optional[str] = Field(None, description="Label describing the prior baseline window")
    current_gmv: Optional[float] = Field(None, description="GMV in current comparison period")
    previous_gmv: Optional[float] = Field(None, description="GMV in prior baseline period")
    gmv_change_pct: Optional[float] = Field(None, description="Percentage change in GMV vs prior period")
    current_net_sales: Optional[float] = Field(None, description="Net sales in current comparison period")
    previous_net_sales: Optional[float] = Field(None, description="Net sales in prior baseline period")
    net_sales_change_pct: Optional[float] = Field(None, description="Percentage change in net sales vs prior period")
    current_transactions: Optional[int] = Field(None, description="Order count in current comparison period")
    previous_transactions: Optional[int] = Field(None, description="Order count in prior baseline period")
    transactions_change_pct: Optional[float] = Field(None, description="Percentage change in orders vs prior period")
    current_aov: Optional[float] = Field(None, description="AOV in current comparison period")
    previous_aov: Optional[float] = Field(None, description="AOV in prior baseline period")
    aov_change_pct: Optional[float] = Field(None, description="Percentage change in AOV vs prior period")
    note: str = Field(..., description="Explanation of comparison window or missing prior baseline")


class ExecutiveCustomerKPIs(BaseModel):
    """Customer acquisition, engagement, and repeat-purchase KPIs."""

    total_registered_customers: Optional[int] = Field(
        None,
        description="Platform registered customer count (null in single-vendor tenant summaries to preserve isolation)",
    )
    purchasing_customers: int = Field(..., description="Distinct customers with orders in the evaluated scope")
    active_customers_90d: int = Field(..., description="Distinct purchasing customers within 90 days of period anchor")
    repeat_customers: int = Field(..., description="Customers with >= 2 transactions in scope")
    repeat_purchase_rate_pct: Optional[float] = Field(
        None, description="Repeat buyers percentage relative to customer denominator"
    )
    avg_customer_spend: float = Field(
        ...,
        description="Average spend per registered customer (platform) or per purchasing customer (date/vendor filtered)",
    )


class ExecutiveVendorSummaryItem(BaseModel):
    """SQL-aggregated vendor sales, market share, commission, and payout record."""

    vendor_id: int
    vendor_name: str
    status: str
    commission_tier: str
    commission_rate: float
    gross_revenue: float
    discounts_allocated: float
    refunds_deducted: float
    net_sales: float
    platform_commission: float
    vendor_payout: float
    units_sold: int
    order_count: int
    rank: int = Field(..., description="Revenue rank (1 = top gross revenue)")
    market_share_pct: float = Field(..., description="Percentage share of total GMV in scope")


class ExecutiveVendorOverview(BaseModel):
    """Vendor ecosystem counts and top-performing sellers."""

    total_vendors: int
    active_vendors: int
    pending_approval_vendors: int
    vendors_with_sales: int
    top_vendor: Optional[ExecutiveVendorSummaryItem] = None
    top_vendors: List[ExecutiveVendorSummaryItem] = Field(default_factory=list)


class ExecutiveProductPerformanceItem(BaseModel):
    """SQL-aggregated product sales, COGS profit (where costed), and stock status."""

    product_id: int
    product_name: str
    category: str
    vendor_id: int
    vendor_name: str
    gross_revenue: float
    net_sales: float
    units_sold: int
    order_count: int
    has_cost_data: bool
    gross_profit_reported: Optional[float] = Field(
        None, description="Gross profit for this SKU only when cost_price exists"
    )
    gross_margin_pct: Optional[float] = Field(
        None, description="Gross margin % for this SKU only when cost_price exists and net_sales > 0"
    )
    current_stock: int
    stock_status: str


class ExecutiveProductOverview(BaseModel):
    """Catalog breadth, top sellers, and cost-coverage summary."""

    total_products: int
    products_with_sales: int
    products_with_cost_data: int
    top_product_by_revenue: Optional[ExecutiveProductPerformanceItem] = None
    top_product_by_units: Optional[ExecutiveProductPerformanceItem] = None
    top_products: List[ExecutiveProductPerformanceItem] = Field(default_factory=list)


class ExecutiveInventoryHealthKPIs(BaseModel):
    """Catalog inventory valuation, stock risk counts, turnover, and DSI metrics."""

    total_skus: int
    total_current_stock: int
    total_stock_valuation: float
    healthy_skus: int
    low_stock_skus: int
    critical_out_of_stock_skus: int
    catalog_turnover_ratio: float
    catalog_dsi_days: float


class ExecutiveSalesTrendPoint(BaseModel):
    """Single chronological bucket (month or day) in executive sales trends."""

    period: str = Field(..., description="YYYY-MM for monthly granularity or YYYY-MM-DD for daily granularity")
    gmv: float
    discounts: float
    refunds: float
    net_sales: float
    units_sold: int
    orders: int
    avg_order_value: float
    growth_pct: Optional[float] = Field(
        None, description="Period-over-period GMV growth % relative to previous chronological bucket"
    )


class ExecutiveSalesGrowthSummary(BaseModel):
    """Monthly growth overview embedded in centralized executive KPI response."""

    latest_period: Optional[str] = None
    latest_mom_growth_pct: Optional[float] = None
    periods_count: int = 0
    monthly_trends: List[ExecutiveSalesTrendPoint] = Field(default_factory=list)


class ExecutiveSummaryResponse(BaseModel):
    """Response schema for GET /analytics/executive/summary (Admin only)."""

    generated_at: str
    filters: DateRangeMetadata
    financials: ExecutiveFinancialKPIs
    period_comparison: PeriodComparisonMetrics
    customers: ExecutiveCustomerKPIs
    vendors: ExecutiveVendorOverview
    products: ExecutiveProductOverview
    inventory_health: ExecutiveInventoryHealthKPIs
    sales_growth: ExecutiveSalesGrowthSummary


class ExecutiveTrendsResponse(BaseModel):
    """Response schema for GET /analytics/executive/trends (Admin only)."""

    generated_at: str
    granularity: str
    filters: DateRangeMetadata
    summary: ExecutiveFinancialKPIs
    period_comparison: PeriodComparisonMetrics
    series: List[ExecutiveSalesTrendPoint]


class ExecutiveVendorProductDrilldownResponse(BaseModel):
    """Response schema for GET /analytics/executive/vendors (Admin only)."""

    generated_at: str
    filters: DateRangeMetadata
    total_gmv: float
    total_net_sales: float
    vendors: List[ExecutiveVendorSummaryItem]
    products: List[ExecutiveProductPerformanceItem]


class ExecutiveVendorTenantSummaryResponse(BaseModel):
    """Tenant-isolated executive KPI summary for GET /analytics/executive/vendor-summary."""

    generated_at: str
    vendor_id: int
    vendor_name: str
    vendor_status: str
    filters: DateRangeMetadata
    financials: ExecutiveFinancialKPIs
    period_comparison: PeriodComparisonMetrics
    customers: ExecutiveCustomerKPIs
    products: ExecutiveProductOverview
    inventory_health: ExecutiveInventoryHealthKPIs
    sales_growth: ExecutiveSalesGrowthSummary

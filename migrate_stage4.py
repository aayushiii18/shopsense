"""
migrate_stage4.py — Safe, idempotent migration for Stage 4: Advanced Commerce & Financial Operations.

Applies:
- Vendors: commission_tier, status, commission_rate, tax_id, business_type, compliance_status, verification_notes.
- Products: cost_price (nullable, preserved NULL on legacy catalog).
- Transactions: payment_method, payment_status, discount_amount, effective_commission_rate.
- Refunds: creates refunds table if not exists, adds returned_quantity, ensures UNIQUE(idempotency_key).
- Vendor Settlements: creates vendor_settlements ledger table.

Guarantees:
- Single atomic transaction block (all-or-nothing).
- 100% idempotent.
- Non-destructive (zero data loss, preserves 600 transactions and 60 customers).
- Zero data fabrication (legacy products retain NULL cost_price, legacy transactions retain NULL commission rate).
"""

import sys
from sqlalchemy import text
from app.database import engine


def run_migration():
    print("Beginning Stage 4 schema migration...")
    with engine.begin() as conn:
        # 1. Update vendors table
        print("Migrating 'vendors' schema...")
        conn.execute(text("""
            ALTER TABLE vendors ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'PENDING_APPROVAL';
        """))
        conn.execute(text("""
            ALTER TABLE vendors ADD COLUMN IF NOT EXISTS commission_tier VARCHAR(50) DEFAULT 'TIER_STANDARD';
        """))
        conn.execute(text("""
            ALTER TABLE vendors ADD COLUMN IF NOT EXISTS commission_rate DOUBLE PRECISION DEFAULT 0.12;
        """))
        conn.execute(text("""
            ALTER TABLE vendors ADD COLUMN IF NOT EXISTS tax_id VARCHAR(100);
        """))
        conn.execute(text("""
            ALTER TABLE vendors ADD COLUMN IF NOT EXISTS business_type VARCHAR(100);
        """))
        conn.execute(text("""
            ALTER TABLE vendors ADD COLUMN IF NOT EXISTS compliance_status VARCHAR(50) DEFAULT 'PENDING_REVIEW';
        """))
        conn.execute(text("""
            ALTER TABLE vendors ADD COLUMN IF NOT EXISTS verification_notes VARCHAR(500);
        """))

        # Update existing 5 seed vendors to LEGACY_ACTIVE and TIER_STANDARD
        conn.execute(text("""
            UPDATE vendors
            SET status = 'LEGACY_ACTIVE',
                commission_tier = 'TIER_STANDARD',
                commission_rate = 0.12,
                compliance_status = 'LEGACY_EXEMPT'
            WHERE id <= 5 AND (status IS NULL OR status = 'PENDING_APPROVAL' OR status = 'LEGACY_ACTIVE');
        """))

        # 2. Update products table
        print("Migrating 'products' schema...")
        conn.execute(text("""
            ALTER TABLE products ADD COLUMN IF NOT EXISTS cost_price DOUBLE PRECISION;
        """))
        # Verify legacy products keep cost_price as NULL
        conn.execute(text("""
            COMMENT ON COLUMN products.cost_price IS 'Unit cost of goods sold. NULL for legacy items without verified invoices.';
        """))

        # 3. Update transactions table
        print("Migrating 'transactions' schema...")
        conn.execute(text("""
            ALTER TABLE transactions ADD COLUMN IF NOT EXISTS payment_method VARCHAR(50) DEFAULT 'UNKNOWN';
        """))
        conn.execute(text("""
            ALTER TABLE transactions ADD COLUMN IF NOT EXISTS payment_status VARCHAR(50) DEFAULT 'COMPLETED';
        """))
        conn.execute(text("""
            ALTER TABLE transactions ADD COLUMN IF NOT EXISTS discount_amount DOUBLE PRECISION DEFAULT 0.0;
        """))
        conn.execute(text("""
            ALTER TABLE transactions ADD COLUMN IF NOT EXISTS effective_commission_rate DOUBLE PRECISION;
        """))
        conn.execute(text("""
            UPDATE transactions SET payment_method = 'UNKNOWN' WHERE payment_method IS NULL;
        """))
        conn.execute(text("""
            UPDATE transactions SET payment_status = 'COMPLETED' WHERE payment_status IS NULL;
        """))
        conn.execute(text("""
            UPDATE transactions SET discount_amount = 0.0 WHERE discount_amount IS NULL;
        """))
        # Historical transactions explicitly keep effective_commission_rate as NULL (zero fabrication)

        # 4. Create or update refunds table
        print("Migrating 'refunds' schema...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS refunds (
                refund_id SERIAL PRIMARY KEY,
                transaction_id INTEGER NOT NULL REFERENCES transactions(transaction_id) ON DELETE RESTRICT,
                idempotency_key VARCHAR(100) UNIQUE NOT NULL,
                amount DOUBLE PRECISION NOT NULL,
                reason VARCHAR(255),
                status VARCHAR(50) NOT NULL DEFAULT 'COMPLETED',
                restock_inventory BOOLEAN NOT NULL DEFAULT FALSE,
                returned_quantity INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
                CONSTRAINT ck_refund_amount_positive CHECK (amount > 0),
                CONSTRAINT ck_refund_returned_quantity_nonnegative CHECK (returned_quantity >= 0)
            );
        """))
        conn.execute(text("""
            ALTER TABLE refunds ADD COLUMN IF NOT EXISTS returned_quantity INTEGER NOT NULL DEFAULT 0;
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_refunds_transaction_id ON refunds (transaction_id);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_refunds_idempotency_key ON refunds (idempotency_key);
        """))

        # 5. Create vendor_settlements ledger table
        print("Migrating 'vendor_settlements' schema...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS vendor_settlements (
                settlement_id SERIAL PRIMARY KEY,
                vendor_id INTEGER NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
                period_start TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                period_end TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                gross_sales DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                discounts_allocated DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                refunds_deducted DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                net_sales DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                commission_tier VARCHAR(50) NOT NULL DEFAULT 'TIER_STANDARD',
                effective_commission_rate DOUBLE PRECISION NOT NULL DEFAULT 0.12,
                platform_commission DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                vendor_payout DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                settlement_status VARCHAR(50) NOT NULL DEFAULT 'DRAFT',
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
            );
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_vendor_settlements_vendor_id ON vendor_settlements (vendor_id);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_vendor_settlements_settlement_id ON vendor_settlements (settlement_id);
        """))

    print("Stage 4 schema migration committed successfully!")


def verify_migration():
    print("Verifying database integrity post-migration...")
    with engine.connect() as conn:
        tx_count = conn.execute(text("SELECT COUNT(*) FROM transactions")).scalar()
        cust_count = conn.execute(text("SELECT COUNT(*) FROM customers")).scalar()
        prod_count = conn.execute(text("SELECT COUNT(*) FROM products")).scalar()
        vendor_count = conn.execute(text("SELECT COUNT(*) FROM vendors")).scalar()
        inv_count = conn.execute(text("SELECT COUNT(*) FROM inventory")).scalar()
        inv_units = conn.execute(text("SELECT SUM(current_stock) FROM inventory")).scalar()
        cost_null_count = conn.execute(text("SELECT COUNT(*) FROM products WHERE cost_price IS NULL")).scalar()
        seed_vendor_status = conn.execute(text("SELECT status, commission_tier, commission_rate FROM vendors WHERE id <= 5")).fetchall()

        print(f"  Transactions: {tx_count} (expected 600)")
        print(f"  Customers:    {cust_count} (expected 60)")
        print(f"  Products:     {prod_count} (expected 10)")
        print(f"  Vendors:      {vendor_count} (expected 5)")
        print(f"  Inventory:    {inv_count} records, {inv_units} units (expected 10 / 990)")
        print(f"  Legacy products with NULL cost_price: {cost_null_count}/10")
        print(f"  Seed vendors status & tier: {seed_vendor_status}")

        assert tx_count == 600, f"Expected 600 transactions, found {tx_count}"
        assert cust_count == 60, f"Expected 60 customers, found {cust_count}"
        assert prod_count == 10, f"Expected 10 products, found {prod_count}"
        assert vendor_count == 5, f"Expected 5 vendors, found {vendor_count}"
        assert inv_units == 990, f"Expected 990 inventory units, found {inv_units}"
        assert cost_null_count == 10, f"Expected all 10 legacy products to have NULL cost_price, found {cost_null_count}"
        for s in seed_vendor_status:
            assert s[0] == "LEGACY_ACTIVE", f"Seed vendor status should be LEGACY_ACTIVE, got {s[0]}"
            assert s[1] == "TIER_STANDARD", f"Seed vendor tier should be TIER_STANDARD, got {s[1]}"
            assert abs(s[2] - 0.12) < 1e-4, f"Seed vendor rate should be 0.12, got {s[2]}"

    print("Post-migration verification PASSED! All invariants preserved.")


if __name__ == "__main__":
    run_migration()
    verify_migration()

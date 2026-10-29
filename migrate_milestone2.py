"""
migrate_milestone2.py — Safe, idempotent migration to Milestone 2 schema.

Applies:
- Creates `customers` table if not exists.
- Adds `parent_category` to `products` if not exists.
- Adds `customer_id` to `transactions` if not exists.
- Creates `stock_movements` table if not exists.
- Creates `customer_interactions` table if not exists.

Guarantees:
- Runs in a single transaction block with commit/rollback.
- Non-destructive (no tables dropped, no data deleted).
- 100% idempotent.
"""

from sqlalchemy import text
from app.database import engine


def run_migration():
    print("Beginning Milestone 2 schema migration...")
    with engine.begin() as conn:
        # 1. Create customers table
        print("Ensuring 'customers' table exists...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS customers (
                customer_id SERIAL PRIMARY KEY,
                name VARCHAR(150) NOT NULL,
                email VARCHAR(254) UNIQUE NOT NULL,
                city VARCHAR(100),
                region VARCHAR(100),
                signup_date TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
            );
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_customers_email ON customers (email);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_customers_customer_id ON customers (customer_id);
        """))

        # 2. Add parent_category to products
        print("Checking 'products' table for 'parent_category' column...")
        conn.execute(text("""
            ALTER TABLE products ADD COLUMN IF NOT EXISTS parent_category VARCHAR(100);
        """))

        # 3. Add customer_id to transactions
        print("Checking 'transactions' table for 'customer_id' column...")
        conn.execute(text("""
            ALTER TABLE transactions ADD COLUMN IF NOT EXISTS customer_id INTEGER;
        """))
        # Add foreign key constraint if not exists
        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_transactions_customer_id'
                ) THEN
                    ALTER TABLE transactions
                    ADD CONSTRAINT fk_transactions_customer_id
                    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
                    ON DELETE SET NULL;
                END IF;
            END $$;
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_transactions_customer_id ON transactions (customer_id);
        """))

        # 4. Create stock_movements table
        print("Ensuring 'stock_movements' table exists...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stock_movements (
                movement_id SERIAL PRIMARY KEY,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                movement_type VARCHAR(50) NOT NULL,
                quantity INTEGER NOT NULL,
                source_warehouse VARCHAR(100),
                target_warehouse VARCHAR(100),
                reference_id INTEGER,
                notes VARCHAR(255),
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
                CONSTRAINT ck_stock_movement_quantity_nonzero CHECK (quantity != 0)
            );
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_stock_movements_movement_id ON stock_movements (movement_id);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_stock_movements_product_id ON stock_movements (product_id);
        """))

        # 5. Create customer_interactions table
        print("Ensuring 'customer_interactions' table exists...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS customer_interactions (
                interaction_id SERIAL PRIMARY KEY,
                customer_id INTEGER NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                interaction_type VARCHAR(50) NOT NULL,
                interaction_weight FLOAT NOT NULL DEFAULT 1.0,
                interaction_date TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
                CONSTRAINT ck_interaction_weight_positive CHECK (interaction_weight > 0)
            );
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_customer_interactions_interaction_id ON customer_interactions (interaction_id);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_customer_interactions_customer_id ON customer_interactions (customer_id);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_customer_interactions_product_id ON customer_interactions (product_id);
        """))

    print("Milestone 2 migration committed successfully!")


if __name__ == "__main__":
    run_migration()

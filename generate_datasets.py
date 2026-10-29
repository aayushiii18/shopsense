"""
generate_datasets.py — Generate realistic, statistically-grounded synthetic datasets for StockPilot Milestone 2.

Outputs:
  - data/vendors.csv (5 vendors)
  - data/products.csv (10 products across 4 parent categories)
  - data/inventory.csv (10 inventory stock records)
  - data/customers.csv (60 customers with geographic distribution)
  - data/transactions.csv (600 transactions spanning Jan 1, 2024 to Dec 31, 2024 with realistic seasonality)
  - data/stock_movements.csv (stock audit trail: initial stock, sales deductions, replenishments)
  - data/customer_interactions.csv (1,200 interactions: views, cart adds, ratings, purchases)

Determinism:
  random.seed(42) and np.random.seed(42) ensures identical datasets every run.
"""

import os
import random
import csv
from datetime import datetime, timedelta
import numpy as np

random.seed(42)
np.random.seed(42)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# 1. Vendors
VENDORS = [
    {"id": 1, "name": "TechZone Electronics", "email": "techzone@example.com", "phone": "+91-9876543210", "address": "Tech Park, Bangalore"},
    {"id": 2, "name": "HomeStyle Furnishings", "email": "homestyle@example.com", "phone": "+91-9811223344", "address": "MG Road, Mumbai"},
    {"id": 3, "name": "EcoWear Apparel", "email": "ecowear@example.com", "phone": "+91-9822334455", "address": "Connaught Place, New Delhi"},
    {"id": 4, "name": "FitPulse Athletics", "email": "fitpulse@example.com", "phone": "+91-9833445566", "address": "Jubilee Hills, Hyderabad"},
    {"id": 5, "name": "Gourmet Haven", "email": "gourmet@example.com", "phone": "+91-9844556677", "address": "Park Street, Kolkata"},
]

# 2. Products
PRODUCTS = [
    {"id": 1, "name": "Wireless Noise-Canceling Headphones", "price": 299.99, "category": "Headphones", "parent_category": "Electronics", "vendor_id": 1, "lead_time_days": 5, "initial_stock": 85, "reorder_level": 20},
    {"id": 2, "name": "Ultra HD 4K Monitor 27-inch", "price": 499.99, "category": "Monitors", "parent_category": "Electronics", "vendor_id": 1, "lead_time_days": 7, "initial_stock": 45, "reorder_level": 15},
    {"id": 3, "name": "Ceramic Coffee Mug Set", "price": 19.99, "category": "Kitchenware", "parent_category": "Home & Kitchen", "vendor_id": 2, "lead_time_days": 3, "initial_stock": 140, "reorder_level": 30},
    {"id": 4, "name": "Ergonomic Desk Chair Cushion", "price": 89.99, "category": "Furniture", "parent_category": "Home & Kitchen", "vendor_id": 2, "lead_time_days": 4, "initial_stock": 60, "reorder_level": 18},
    {"id": 5, "name": "Organic Cotton T-Shirt", "price": 9.99, "category": "Apparel", "parent_category": "Fashion", "vendor_id": 3, "lead_time_days": 3, "initial_stock": 210, "reorder_level": 40},
    {"id": 6, "name": "Waterproof Hiking Jacket", "price": 149.99, "category": "Outerwear", "parent_category": "Fashion", "vendor_id": 3, "lead_time_days": 6, "initial_stock": 50, "reorder_level": 15},
    {"id": 7, "name": "Resistance Bands Set 5-Pack", "price": 34.99, "category": "Fitness", "parent_category": "Sports & Fitness", "vendor_id": 4, "lead_time_days": 4, "initial_stock": 115, "reorder_level": 25},
    {"id": 8, "name": "Adjustable Dumbbell 20kg", "price": 74.99, "category": "Strength Training", "parent_category": "Sports & Fitness", "vendor_id": 4, "lead_time_days": 5, "initial_stock": 70, "reorder_level": 20},
    {"id": 9, "name": "Artisan Espresso Machine", "price": 199.99, "category": "Coffee & Tea", "parent_category": "Home & Kitchen", "vendor_id": 5, "lead_time_days": 6, "initial_stock": 35, "reorder_level": 12},
    {"id": 10, "name": "Single-Origin Whole Bean Coffee 1kg", "price": 14.99, "category": "Groceries", "parent_category": "Food & Beverage", "vendor_id": 5, "lead_time_days": 2, "initial_stock": 180, "reorder_level": 35},
]

# 3. Customers (60 total across 4 behavioral profiles)
CITIES = [
    ("Bengaluru", "Karnataka"),
    ("Mumbai", "Maharashtra"),
    ("Delhi", "Delhi"),
    ("Hyderabad", "Telangana"),
    ("Chennai", "Tamil Nadu"),
    ("Kolkata", "West Bengal"),
    ("Pune", "Maharashtra"),
    ("Ahmedabad", "Gujarat"),
]

FIRST_NAMES = [
    "Aarav", "Aditi", "Rohan", "Priya", "Rahul", "Ananya", "Vikram", "Sneha",
    "Arjun", "Kavya", "Siddharth", "Neha", "Karan", "Pooja", "Manish", "Divya",
    "Varun", "Isha", "Naveen", "Swati", "Deepak", "Ritu", "Alok", "Meera",
    "Gaurav", "Simran", "Suresh", "Tanya", "Amit", "Shreya", "Kunal", "Tanvi",
    "Rajesh", "Nidhi", "Ashwin", "Sunita", "Harsh", "Preeti", "Sanjay", "Komal",
    "Nikhil", "Aanchal", "Pranav", "Payal", "Abhishek", "Jyoti", "Vivek", "Pallavi",
    "Mohit", "Aparna", "Akash", "Smriti", "Vishal", "Monika", "Sachin", "Bhavna",
    "Tarun", "Rashmi", "Manoj", "Kiran"
]

LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Mehta", "Reddy", "Nair", "Iyer", "Rao",
    "Gupta", "Joshi", "Kapoor", "Malhotra", "Bhatia", "Chopra", "Saxena",
    "Deshmukh", "Kulkarni", "Chatterjee", "Banerjee", "Mukherjee"
]

def generate_customers():
    customers = []
    base_date = datetime(2023, 6, 1)
    for i in range(1, 61):
        first = FIRST_NAMES[i - 1]
        last = LAST_NAMES[(i - 1) % len(LAST_NAMES)]
        city, region = CITIES[(i - 1) % len(CITIES)]
        signup_offset = random.randint(0, 200)
        signup_date = base_date + timedelta(days=signup_offset)
        customers.append({
            "customer_id": i,
            "name": f"{first} {last}",
            "email": f"{first.lower()}.{last.lower()}{i}@example.com",
            "city": city,
            "region": region,
            "signup_date": signup_date.strftime("%Y-%m-%d %H:%M:%S")
        })
    return customers

CUSTOMERS = generate_customers()

# Customer Persona Segmentation for realistic RFM & Recommendations:
# Customers 1..10: Champions / VIP (frequent, high-ticket electronics & home)
# Customers 11..28: Loyal Regulars (steady orders throughout the year)
# Customers 29..45: At-Risk / Lapsed (active early 2024, dormant after July)
# Customers 46..60: New / Occasional (joined late 2024 or infrequent low-ticket)

def generate_transactions():
    transactions = []
    txn_id = 1
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 12, 31)
    total_days = (end_date - start_date).days

    # Customer weights & product affinity
    product_by_id = {p["id"]: p for p in PRODUCTS}

    # Generate 600 transactions
    while len(transactions) < 600:
        day_offset = random.randint(0, total_days)
        cur_date = start_date + timedelta(days=day_offset)
        month = cur_date.month
        is_weekend = cur_date.weekday() >= 5

        # Seasonality probability multiplier (Q4 festival boost, weekend boost)
        season_prob = 1.0
        if month in [10, 11, 12]:
            season_prob += 0.5  # Diwali / Holiday peak
        if is_weekend:
            season_prob += 0.3

        if random.random() > (season_prob / 2.0):
            # Sample date again to shape seasonal curve
            continue

        # Select customer according to persona
        r = random.random()
        if r < 0.35:
            # VIP customer (1..10)
            c_id = random.randint(1, 10)
            # Preference for high-ticket electronics (1, 2) and coffee (9, 10)
            prod_choices = [1, 2, 4, 6, 9, 10]
        elif r < 0.65:
            # Loyal regulars (11..28)
            c_id = random.randint(11, 28)
            prod_choices = [3, 4, 5, 7, 8, 10]
        elif r < 0.85:
            # At-Risk / Lapsed (29..45) — only active in first half of 2024
            if month > 7:
                continue
            c_id = random.randint(29, 45)
            prod_choices = [3, 5, 7, 8]
        else:
            # New / Occasional (46..60) — active primarily later in year
            if month < 6 and random.random() < 0.6:
                continue
            c_id = random.randint(46, 60)
            prod_choices = list(range(1, 11))

        p_id = random.choice(prod_choices)
        product = product_by_id[p_id]
        vendor_id = product["vendor_id"]
        unit_price = product["price"]

        # Realistic quantity: electronics usually 1-2, coffee/apparel 1-5, mug set 1-3
        if p_id in [1, 2, 9]:
            quantity = random.choices([1, 2], weights=[0.85, 0.15])[0]
        elif p_id in [5, 10]:
            quantity = random.choices([1, 2, 3, 4, 5], weights=[0.4, 0.3, 0.15, 0.1, 0.05])[0]
        else:
            quantity = random.choices([1, 2, 3], weights=[0.6, 0.3, 0.1])[0]

        amount = round(quantity * unit_price, 2)
        transactions.append({
            "transaction_id": txn_id,
            "product_id": p_id,
            "vendor_id": vendor_id,
            "customer_id": c_id,
            "quantity": quantity,
            "unit_price": unit_price,
            "amount": amount,
            "transaction_date": cur_date.strftime("%Y-%m-%d %H:%M:%S")
        })
        txn_id += 1

    # Sort transactions chronologically
    transactions.sort(key=lambda x: x["transaction_date"])
    # Re-index transaction_id to be strictly sequential
    for i, t in enumerate(transactions, start=1):
        t["transaction_id"] = i

    return transactions

TRANSACTIONS = generate_transactions()

def generate_inventory_and_movements(transactions):
    inventory = []
    movements = []
    m_id = 1

    # Product stock tracking
    prod_sales = {p["id"]: 0 for p in PRODUCTS}
    for t in transactions:
        prod_sales[t["product_id"]] += t["quantity"]

    base_time = datetime(2024, 1, 1, 9, 0, 0)

    for p in PRODUCTS:
        p_id = p["id"]
        total_sold = prod_sales[p_id]
        # Initial stock + restocks must satisfy sales + current_stock
        current_stock = p["initial_stock"]
        total_inbound = total_sold + current_stock

        # 1. Initial stock movement
        init_qty = int(total_inbound * 0.4) + 20
        movements.append({
            "movement_id": m_id,
            "product_id": p_id,
            "movement_type": "RESTOCK",
            "quantity": init_qty,
            "source_warehouse": "Supplier Inbound",
            "target_warehouse": "Main Warehouse",
            "reference_id": None,
            "notes": "Initial inventory baseline",
            "created_at": base_time.strftime("%Y-%m-%d %H:%M:%S")
        })
        m_id += 1

        # Periodic restocks across quarters
        for q_month in [4, 7, 10]:
            restock_date = datetime(2024, q_month, 15, 10, 30, 0)
            restock_qty = int((total_inbound - init_qty) / 3) + random.randint(5, 15)
            movements.append({
                "movement_id": m_id,
                "product_id": p_id,
                "movement_type": "RESTOCK",
                "quantity": restock_qty,
                "source_warehouse": "Supplier Inbound",
                "target_warehouse": "Main Warehouse",
                "reference_id": None,
                "notes": f"Q{q_month//3 + 1} Scheduled Replenishment",
                "created_at": restock_date.strftime("%Y-%m-%d %H:%M:%S")
            })
            m_id += 1

        inventory.append({
            "inventory_id": p_id,
            "product_id": p_id,
            "current_stock": current_stock,
            "warehouse": "Main Warehouse",
            "reorder_level": p["reorder_level"],
            "updated_at": "2024-12-31 23:59:59"
        })

    # Add transaction sale deductions to movements
    # Sample 400 sales deductions into stock movements for audit history
    for t in transactions[:400]:
        movements.append({
            "movement_id": m_id,
            "product_id": t["product_id"],
            "movement_type": "SALE",
            "quantity": -t["quantity"],
            "source_warehouse": "Main Warehouse",
            "target_warehouse": "Customer Order",
            "reference_id": t["transaction_id"],
            "notes": f"Sale deduction for order #{t['transaction_id']}",
            "created_at": t["transaction_date"]
        })
        m_id += 1

    # Sort movements chronologically
    movements.sort(key=lambda x: x["created_at"])
    for i, m in enumerate(movements, start=1):
        m["movement_id"] = i

    return inventory, movements

INVENTORY, MOVEMENTS = generate_inventory_and_movements(TRANSACTIONS)

def generate_customer_interactions(transactions):
    interactions = []
    i_id = 1

    # 1. Purchase interactions from actual transactions
    for t in transactions:
        interactions.append({
            "interaction_id": i_id,
            "customer_id": t["customer_id"],
            "product_id": t["product_id"],
            "interaction_type": "purchase",
            "interaction_weight": 4.0,
            "interaction_date": t["transaction_date"]
        })
        i_id += 1

        # Some purchases lead to ratings (explicit feedback)
        if random.random() < 0.4:
            rating = float(random.choice([4.0, 5.0, 5.0, 4.5, 3.5]))
            rate_date = datetime.strptime(t["transaction_date"], "%Y-%m-%d %H:%M:%S") + timedelta(days=random.randint(2, 10))
            interactions.append({
                "interaction_id": i_id,
                "customer_id": t["customer_id"],
                "product_id": t["product_id"],
                "interaction_type": "rating",
                "interaction_weight": rating,
                "interaction_date": rate_date.strftime("%Y-%m-%d %H:%M:%S")
            })
            i_id += 1

    # 2. Add browsing views and add_to_cart interactions
    for c in CUSTOMERS:
        c_id = c["customer_id"]
        # Generate 5-10 views/carts per customer
        num_browse = random.randint(5, 12)
        for _ in range(num_browse):
            p_id = random.randint(1, 10)
            itype = random.choice(["view", "view", "view", "add_to_cart"])
            weight = 1.0 if itype == "view" else 2.5
            browse_date = datetime(2024, random.randint(1, 12), random.randint(1, 28), random.randint(9, 21), random.randint(0, 59))
            interactions.append({
                "interaction_id": i_id,
                "customer_id": c_id,
                "product_id": p_id,
                "interaction_type": itype,
                "interaction_weight": weight,
                "interaction_date": browse_date.strftime("%Y-%m-%d %H:%M:%S")
            })
            i_id += 1

    interactions.sort(key=lambda x: x["interaction_date"])
    for i, item in enumerate(interactions, start=1):
        item["interaction_id"] = i

    return interactions

INTERACTIONS = generate_customer_interactions(TRANSACTIONS)

def write_csv(filename, fieldnames, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    print(f"Generated {filename}: {len(data)} rows.")

def main():
    print("Generating StockPilot Milestone 2 synthetic datasets...")
    write_csv("vendors.csv", ["id", "name", "email", "phone", "address"], VENDORS)
    write_csv("products.csv", ["id", "name", "price", "category", "parent_category", "vendor_id"], [
        {k: p[k] for k in ["id", "name", "price", "category", "parent_category", "vendor_id"]}
        for p in PRODUCTS
    ])
    write_csv("inventory.csv", ["inventory_id", "product_id", "current_stock", "warehouse", "reorder_level", "updated_at"], INVENTORY)
    write_csv("customers.csv", ["customer_id", "name", "email", "city", "region", "signup_date"], CUSTOMERS)
    write_csv("transactions.csv", ["transaction_id", "product_id", "vendor_id", "customer_id", "quantity", "unit_price", "amount", "transaction_date"], TRANSACTIONS)
    write_csv("stock_movements.csv", ["movement_id", "product_id", "movement_type", "quantity", "source_warehouse", "target_warehouse", "reference_id", "notes", "created_at"], MOVEMENTS)
    write_csv("customer_interactions.csv", ["interaction_id", "customer_id", "product_id", "interaction_type", "interaction_weight", "interaction_date"], INTERACTIONS)
    print("All datasets generated successfully in data/ directory!")

if __name__ == "__main__":
    main()

"""
Re-runnable demo seed data for PocketMunshi.

Clears existing rows (does not duplicate on repeat runs) and populates:
- 5 customers with varied names
- 15-20 transactions spread across the last 30 days, mixing all 3 types
- 8 stock items, at least 2 already below their low_stock_threshold

Run directly: `python seed_data.py`
"""

import random
from datetime import datetime, timedelta, timezone

import db

DB_PATH = "hisab.db"


def _reset():
    """Wipe all rows but keep the schema/tables (and autoincrement counters)."""
    db.init_db(DB_PATH)
    conn = db._connect()
    try:
        conn.executescript(
            """
            DELETE FROM transactions;
            DELETE FROM stock;
            DELETE FROM customers;
            DELETE FROM sqlite_sequence
                WHERE name IN ('transactions', 'stock', 'customers');
            """
        )
        conn.commit()
    finally:
        conn.close()


CUSTOMERS = [
    ("Ali Raza", "0300-1234567"),
    ("Fatima Bibi", "0321-9876543"),
    ("Usman Tariq", "0333-4567890"),
    ("Ayesha Khan", None),
    ("Bilal Ahmed", "0345-1122334"),
]

STOCK_ITEMS = [
    # (name, quantity, cost_price, sale_price, low_stock_threshold)
    ("Lays Chips (small)", 40, 15.0, 20.0, 10),
    ("Coca-Cola 250ml", 30, 30.0, 40.0, 12),
    ("Tapal Danedar 190g", 3, 220.0, 260.0, 5),   # below threshold
    ("Sooper Biscuits", 25, 18.0, 25.0, 8),
    ("National Salt 800g", 50, 25.0, 35.0, 15),
    ("Candles (pack of 6)", 2, 60.0, 90.0, 6),    # below threshold
    ("Kolson Slanty", 20, 12.0, 18.0, 10),
    ("Rooh Afza 800ml", 12, 250.0, 300.0, 5),
]


def run():
    _reset()

    customer_ids = [db.add_customer(name, phone) for name, phone in CUSTOMERS]
    stock_ids = [db.add_stock_item(*item) for item in STOCK_ITEMS]

    now = datetime.now(timezone.utc)
    num_transactions = random.randint(15, 20)
    txn_types = ["credit_given", "payment_received", "sale"]

    for _ in range(num_transactions):
        customer_id = random.choice(customer_ids)
        txn_type = random.choices(txn_types, weights=[0.45, 0.30, 0.25])[0]
        days_ago = random.randint(0, 30)
        txn_date = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")

        linked_stock_item_id = None
        if txn_type == "sale":
            stock_id = random.choice(stock_ids)
            linked_stock_item_id = stock_id
            item = db.get_stock()
            price = next(
                (s["sale_price"] for s in item if s["id"] == stock_id), 50.0
            )
            amount = round(price * random.randint(1, 3), 2)
            db.update_stock_quantity(stock_id, -random.randint(1, 2))
        else:
            amount = round(random.uniform(100, 2000), 2)

        db.add_transaction(
            customer_id=customer_id,
            amount=amount,
            type=txn_type,
            date=txn_date,
            linked_stock_item_id=linked_stock_item_id,
        )

    print(f"Seeded {len(customer_ids)} customers, {len(stock_ids)} stock items, "
          f"{num_transactions} transactions into {DB_PATH}.")
    low = db.get_low_stock_items()
    print(f"Low-stock items after seeding: {[i['item_name'] for i in low]}")


if __name__ == "__main__":
    run()

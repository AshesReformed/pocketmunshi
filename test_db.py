"""
Standalone self-test for db.py. Run: `python test_db.py`
Exercises every function in the interface contract and asserts correctness,
including the low-stock threshold boundary (just-above vs just-below).
Uses its own throwaway DB file so it never touches hisab.db / demo data.
"""

import os

import db

TEST_DB = "test_hisab.db"


def setup():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    db.init_db(TEST_DB)


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, f"FAILED: {label}"


def main():
    setup()

    # --- customers ---
    cid = db.add_customer("Test Customer", "0300-0000000")
    check("add_customer returns an int id", isinstance(cid, int))
    customers = db.get_customers()
    check("get_customers returns the new customer", any(c["id"] == cid for c in customers))
    check("new customer starts at balance 0", db.get_customer_balance(cid) == 0)

    # --- transactions: balance math ---
    t1 = db.add_transaction(cid, 500, "credit_given")
    t2 = db.add_transaction(cid, 200, "payment_received")
    check(
        "balance = credit_given - payment_received",
        db.get_customer_balance(cid) == 300,
    )

    # --- update_transaction reflects immediately ---
    db.update_transaction(t2, amount=500)
    check(
        "update_transaction changes balance immediately",
        db.get_customer_balance(cid) == 0,
    )

    # --- delete_transaction reflects immediately ---
    db.delete_transaction(t2)
    check(
        "delete_transaction changes balance immediately",
        db.get_customer_balance(cid) == 500,
    )

    # --- get_transactions filters by customer ---
    other = db.add_customer("Other Customer")
    db.add_transaction(other, 999, "credit_given")
    txns_for_cid = db.get_transactions(cid)
    check(
        "get_transactions(customer_id) only returns that customer's rows",
        all(t["customer_id"] == cid for t in txns_for_cid),
    )
    all_txns = db.get_transactions()
    check(
        "get_transactions() with no arg returns all customers' rows",
        len(all_txns) >= len(txns_for_cid) + 1,
    )

    # --- stock + sale linkage ---
    item_id = db.add_stock_item("Test Item", quantity=10, cost_price=5, sale_price=8,
                                 low_stock_threshold=5)
    db.add_transaction(cid, 8, "sale", linked_stock_item_id=item_id)
    db.update_stock_quantity(item_id, -1)
    stock = db.get_stock()
    qty = next(s["quantity"] for s in stock if s["id"] == item_id)
    check("update_stock_quantity reduces quantity on sale", qty == 9)

    # --- low stock boundary: exactly AT threshold is NOT low ---
    db.update_stock_quantity(item_id, -4)  # 9 -> 5, equal to threshold
    low_at_boundary = [i["id"] for i in db.get_low_stock_items()]
    check(
        "quantity == threshold is NOT flagged low (just-above/at boundary)",
        item_id not in low_at_boundary,
    )

    # --- low stock boundary: just BELOW threshold IS low ---
    db.update_stock_quantity(item_id, -1)  # 5 -> 4, below threshold of 5
    low_below_boundary = [i["id"] for i in db.get_low_stock_items()]
    check(
        "quantity < threshold IS flagged low (just-below boundary)",
        item_id in low_below_boundary,
    )

    # --- overdue customers ---
    overdue_cid = db.add_customer("Overdue Customer")
    old_date = "2000-01-01 00:00:00"
    db.add_transaction(overdue_cid, 1000, "credit_given", date=old_date)
    overdue = db.get_overdue_customers(days=7)
    check(
        "get_overdue_customers flags a customer with balance > 0 and an old txn",
        any(o["id"] == overdue_cid for o in overdue),
    )
    paid_cid = db.add_customer("Paid-Up Customer")
    db.add_transaction(paid_cid, 100, "credit_given", date=old_date)
    db.add_transaction(paid_cid, 100, "payment_received", date=old_date)
    overdue2 = db.get_overdue_customers(days=7)
    check(
        "get_overdue_customers excludes customers with balance <= 0",
        all(o["id"] != paid_cid for o in overdue2),
    )

    # --- export_all_to_csv ---
    paths = db.export_all_to_csv("test_csv_export")
    check("export_all_to_csv writes 3 files", len(paths) == 3)
    check("export_all_to_csv files all exist", all(os.path.exists(p) for p in paths))

    print("\nAll db.py checks passed.")


if __name__ == "__main__":
    main()

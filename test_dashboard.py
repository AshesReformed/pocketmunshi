"""
Self-test for dashboard.py's pure computation logic (no Streamlit/Plotly
needed -- those imports are lazy, inside the render_* functions).
Run: `python test_dashboard.py`
"""

from datetime import datetime, timedelta, timezone

import dashboard


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, f"FAILED: {label}"


def main():
    today = datetime.now(timezone.utc).date()
    today_str = today.strftime("%Y-%m-%d %H:%M:%S")
    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

    stock_items = [
        {"id": 1, "item_name": "Chips", "quantity": 10, "cost_price": 15.0,
         "sale_price": 20.0, "low_stock_threshold": 5},
    ]

    # sale of 2 units (revenue = 40, cost = 2*15 = 30, profit = 10)
    transactions = [
        {"type": "sale", "amount": 40.0, "date": today_str, "linked_stock_item_id": 1},
        {"type": "credit_given", "amount": 500.0, "date": today_str, "linked_stock_item_id": None},
        {"type": "sale", "amount": 25.0, "date": yesterday_str, "linked_stock_item_id": None},
    ]

    pnl_today = dashboard.compute_daily_pnl(transactions, stock_items, today)
    check("linked sale profit = revenue - cost basis (40 - 30 = 10)", pnl_today == 10.0)
    check("credit_given is excluded from P&L", pnl_today != 510.0)

    pnl_yesterday = dashboard.compute_daily_pnl(transactions, stock_items, today - timedelta(days=1))
    check(
        "unlinked sale counts full revenue as profit (documented fallback)",
        pnl_yesterday == 25.0,
    )

    series = dashboard.compute_pnl_series(transactions, stock_items, num_days=30)
    check("compute_pnl_series returns num_days entries", len(series) == 30)
    check("compute_pnl_series is oldest-first", series[-1][0] == today)
    check(
        "compute_pnl_series today's value matches compute_daily_pnl",
        series[-1][1] == pnl_today,
    )

    print("\nAll dashboard.py computation checks passed.")


if __name__ == "__main__":
    main()

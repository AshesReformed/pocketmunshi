"""
PocketMunshi dashboard: P&L, stock, and overdue-reminders views.

Pure computation lives in module-level helper functions (no Streamlit
dependency) so they're unit-testable standalone; render_* functions are thin
Streamlit/Plotly wrappers around them.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd

import db


def _parse_date(date_str: str) -> datetime:
    """Accepts either 'YYYY-MM-DD HH:MM:SS' or plain 'YYYY-MM-DD'."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {date_str!r}")


def _profit_for_sale_txn(txn: dict, stock_by_id: dict) -> float:
    """
    Profit for one 'sale' transaction = revenue - cost basis.

    The schema stores only the total sale amount (revenue), not a quantity,
    so cost basis is derived as (amount / sale_price) * cost_price for the
    linked stock item. A sale with no linked stock item has no known cost
    basis, so its full amount is counted as profit (documented assumption,
    not a bug) -- most sales should be linked for accurate P&L.
    """
    if txn["type"] != "sale":
        return 0.0
    revenue = txn["amount"]
    stock_id = txn.get("linked_stock_item_id")
    item = stock_by_id.get(stock_id) if stock_id is not None else None
    if item is None or not item.get("sale_price"):
        return revenue
    quantity = revenue / item["sale_price"]
    cost = quantity * item["cost_price"]
    return revenue - cost


def compute_daily_pnl(transactions: list[dict], stock_items: list[dict], target_date) -> float:
    """Sum of profit across all 'sale' transactions on target_date (a date object)."""
    stock_by_id = {s["id"]: s for s in stock_items}
    total = 0.0
    for t in transactions:
        if t["type"] != "sale":
            continue
        if _parse_date(t["date"]).date() != target_date:
            continue
        total += _profit_for_sale_txn(t, stock_by_id)
    return round(total, 2)


def compute_pnl_series(transactions: list[dict], stock_items: list[dict], num_days: int = 30):
    """Returns a list of (date, pnl) tuples for the last num_days days, oldest first."""
    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=i) for i in range(num_days - 1, -1, -1)]
    return [(d, compute_daily_pnl(transactions, stock_items, d)) for d in days]


def render_pnl_dashboard(db_path: str) -> None:
    import plotly.express as px
    import streamlit as st

    db.init_db(db_path)
    transactions = db.get_transactions()
    stock_items = db.get_stock()

    today = datetime.now(timezone.utc).date()
    today_pnl = compute_daily_pnl(transactions, stock_items, today)

    st.subheader("Profit & Loss")
    st.metric("Today's Profit/Loss", f"Rs {today_pnl:,.2f}")

    series = compute_pnl_series(transactions, stock_items, num_days=30)
    if not any(pnl for _, pnl in series):
        st.info("No sales recorded yet in the last 30 days.")
        return

    df = pd.DataFrame(series, columns=["date", "profit_loss"])
    fig = px.line(
        df,
        x="date",
        y="profit_loss",
        title="30-Day Profit/Loss Trend",
        color_discrete_sequence=["#2E7D32"],
    )
    fig.update_traces(mode="lines+markers")
    fig.update_layout(yaxis_title="Profit/Loss (Rs)", xaxis_title="Date")
    st.plotly_chart(fig, use_container_width=True)


def render_stock_view(db_path: str) -> None:
    import streamlit as st

    db.init_db(db_path)
    stock_items = db.get_stock()
    low_stock_ids = {i["id"] for i in db.get_low_stock_items()}

    st.subheader("Stock")
    if not stock_items:
        st.info("No stock items yet.")
        return

    rows = []
    for item in stock_items:
        rows.append(
            {
                "Item": item["item_name"],
                "Quantity": item["quantity"],
                "Cost Price": item["cost_price"],
                "Sale Price": item["sale_price"],
                "Low Stock Threshold": item["low_stock_threshold"],
                "Status": "⚠️ Low Stock" if item["id"] in low_stock_ids else "OK",
            }
        )
    df = pd.DataFrame(rows)

    def _highlight_low(row):
        color = "background-color: #ffebee" if row["Status"] != "OK" else ""
        return [color] * len(row)

    st.dataframe(df.style.apply(_highlight_low, axis=1), use_container_width=True)

    if low_stock_ids:
        st.warning(f"{len(low_stock_ids)} item(s) are below their low-stock threshold.")


def render_reminders_view(db_path: str) -> None:
    import streamlit as st

    db.init_db(db_path)
    overdue = db.get_overdue_customers(days=7)

    st.subheader("Overdue Udhaar Reminders")
    if not overdue:
        st.success("No overdue customers — everyone is within 7 days.")
        return

    df = pd.DataFrame(
        [
            {
                "Customer": c["name"],
                "Phone": c["phone"] or "—",
                "Balance Owed (Rs)": c["balance"],
                "Days Since Last Transaction": c["days_since_last_txn"],
            }
            for c in overdue
        ]
    )
    st.dataframe(df, use_container_width=True)

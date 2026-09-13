"""
PocketMunshi data layer.

SQLite-only, single-file storage (default: hisab.db). Implements the exact
interface contract shared across the PocketMunshi build (see
PocketMunshi_Claude_Kickoff_Instructions.md, Prompt 1).

Notes on design choices:
- A module-level DB_PATH is set by init_db() and reused by every other
  function, since the contract doesn't thread a path through every call.
- get_customer_balance() is derived on the fly from transactions rather than
  cached on the customers table, so edits/deletes are reflected immediately
  with no separate invalidation step.
- Streamlit Community Cloud's filesystem is NOT persistent across
  reboots/redeploys -- a written SQLite file can be silently wiped when the
  app sleeps and restarts. export_all_to_csv() exists as the safety net for
  this; treat it as required, not optional.
"""

import csv
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = "hisab.db"

_VALID_TXN_TYPES = {"credit_given", "payment_received", "sale"}


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def init_db(path: str = "hisab.db") -> None:
    """Create the database file and schema if they don't already exist."""
    global DB_PATH
    DB_PATH = path
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT
            );

            CREATE TABLE IF NOT EXISTS stock (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                cost_price REAL NOT NULL DEFAULT 0,
                sale_price REAL NOT NULL DEFAULT 0,
                low_stock_threshold INTEGER NOT NULL DEFAULT 5
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                type TEXT NOT NULL,
                linked_stock_item_id INTEGER,
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                FOREIGN KEY (linked_stock_item_id) REFERENCES stock(id)
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def add_customer(name: str, phone: str | None = None) -> int:
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO customers (name, phone) VALUES (?, ?)", (name, phone)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_customers() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT id, name, phone FROM customers").fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["balance"] = get_customer_balance(d["id"])
            result.append(d)
        return result
    finally:
        conn.close()


def add_transaction(
    customer_id: int,
    amount: float,
    type: str,
    date: str | None = None,
    linked_stock_item_id: int | None = None,
) -> int:
    if type not in _VALID_TXN_TYPES:
        raise ValueError(
            f"Invalid transaction type {type!r}; must be one of {_VALID_TXN_TYPES}"
        )
    date = date or _now_str()
    conn = _connect()
    try:
        cur = conn.execute(
            """INSERT INTO transactions
               (customer_id, date, amount, type, linked_stock_item_id)
               VALUES (?, ?, ?, ?, ?)""",
            (customer_id, date, amount, type, linked_stock_item_id),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_transactions(customer_id: int | None = None) -> list[dict]:
    conn = _connect()
    try:
        if customer_id is None:
            rows = conn.execute(
                "SELECT * FROM transactions ORDER BY date DESC, id DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM transactions WHERE customer_id = ? "
                "ORDER BY date DESC, id DESC",
                (customer_id,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_transaction(transaction_id: int, **fields) -> None:
    if not fields:
        return
    allowed = {"customer_id", "date", "amount", "type", "linked_stock_item_id"}
    bad = set(fields) - allowed
    if bad:
        raise ValueError(f"Unknown transaction field(s): {bad}")
    if "type" in fields and fields["type"] not in _VALID_TXN_TYPES:
        raise ValueError(f"Invalid transaction type {fields['type']!r}")
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [transaction_id]
    conn = _connect()
    try:
        conn.execute(f"UPDATE transactions SET {set_clause} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


def delete_transaction(transaction_id: int) -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        conn.commit()
    finally:
        conn.close()


def get_customer_balance(customer_id: int) -> float:
    """balance = sum(credit_given) - sum(payment_received) for this customer."""
    conn = _connect()
    try:
        row = conn.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN type = 'credit_given' THEN amount ELSE 0 END), 0)
                 - COALESCE(SUM(CASE WHEN type = 'payment_received' THEN amount ELSE 0 END), 0)
                 AS balance
               FROM transactions WHERE customer_id = ?""",
            (customer_id,),
        ).fetchone()
        return float(row["balance"]) if row and row["balance"] is not None else 0.0
    finally:
        conn.close()


def get_overdue_customers(days: int = 7) -> list[dict]:
    """Customers with balance > 0, sorted by days since their most recent transaction (desc)."""
    conn = _connect()
    try:
        customers = conn.execute("SELECT id, name, phone FROM customers").fetchall()
        now = datetime.now(timezone.utc)
        result = []
        for c in customers:
            balance = get_customer_balance(c["id"])
            if balance <= 0:
                continue
            last_txn = conn.execute(
                "SELECT date FROM transactions WHERE customer_id = ? "
                "ORDER BY date DESC LIMIT 1",
                (c["id"],),
            ).fetchone()
            if last_txn is None:
                continue
            try:
                last_date = datetime.strptime(last_txn["date"], "%Y-%m-%d %H:%M:%S")
                last_date = last_date.replace(tzinfo=timezone.utc)
            except ValueError:
                # fall back for date-only strings ("YYYY-MM-DD")
                last_date = datetime.strptime(last_txn["date"], "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            days_since = (now - last_date).days
            if days_since >= days:
                result.append(
                    {
                        "id": c["id"],
                        "name": c["name"],
                        "phone": c["phone"],
                        "balance": balance,
                        "days_since_last_txn": days_since,
                    }
                )
        result.sort(key=lambda x: x["days_since_last_txn"], reverse=True)
        return result
    finally:
        conn.close()


def add_stock_item(
    item_name: str,
    quantity: int,
    cost_price: float,
    sale_price: float,
    low_stock_threshold: int = 5,
) -> int:
    conn = _connect()
    try:
        cur = conn.execute(
            """INSERT INTO stock
               (item_name, quantity, cost_price, sale_price, low_stock_threshold)
               VALUES (?, ?, ?, ?, ?)""",
            (item_name, quantity, cost_price, sale_price, low_stock_threshold),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_stock() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM stock").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_stock_quantity(item_id: int, delta: int) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE stock SET quantity = quantity + ? WHERE id = ?", (delta, item_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_low_stock_items() -> list[dict]:
    """quantity < low_stock_threshold (strictly below -- at-threshold is NOT low)."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM stock WHERE quantity < low_stock_threshold"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def export_all_to_csv(output_dir: str) -> list[str]:
    """Dump every table to CSV. Safety net against Streamlit Cloud's ephemeral disk."""
    os.makedirs(output_dir, exist_ok=True)
    conn = _connect()
    written = []
    try:
        for table in ("customers", "transactions", "stock"):
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            path = os.path.join(output_dir, f"{table}.csv")
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if rows:
                    writer.writerow(rows[0].keys())
                    for r in rows:
                        writer.writerow(list(r))
                else:
                    # still write a header so the file isn't empty/ambiguous
                    cols = [
                        c[1]
                        for c in conn.execute(f"PRAGMA table_info({table})").fetchall()
                    ]
                    writer.writerow(cols)
            written.append(path)
        return written
    finally:
        conn.close()

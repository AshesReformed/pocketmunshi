"""
PocketMunshi main Streamlit app: auth gate, voice entry, ledger, and stock,
wired to dashboard.py for P&L/reminders. Run with: `streamlit run app.py`

Secrets required (see .streamlit/secrets.toml.example):
    shop_username, shop_password   -- hardcoded shop-owner login
    GROQ_API_KEY                   -- for voice.py / extract.py
"""

import streamlit as st
from audio_recorder_streamlit import audio_recorder

import dashboard
import db
from extract import extract_transaction
from voice import transcribe_audio

DB_PATH = "hisab.db"
CSV_BACKUP_DIR = "csv_backup"
TXN_TYPES = ["credit_given", "payment_received", "sale"]
TXN_TYPE_LABELS = {
    "credit_given": "Credit Given (udhaar)",
    "payment_received": "Payment Received",
    "sale": "Cash Sale",
}


def init_state():
    defaults = {
        "authenticated": False,
        "pending_transcript": "",
        "pending_transaction": None,
        "_last_audio_bytes": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def login_gate():
    st.title("\U0001F4D2 PocketMunshi")
    st.caption("Voice-first udhaar ledger for shopkeepers")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log In")

    if submitted:
        expected_user = st.secrets.get("shop_username", "")
        expected_pass = st.secrets.get("shop_password", "")
        if username == expected_user and password == expected_pass and username:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect username or password.")


def _save_transaction(customer_name: str, amount: float, txn_type: str,
                       linked_stock_item_id=None):
    """Look up or create the customer by name, then record the transaction."""
    customer_name = customer_name.strip()
    customers = db.get_customers()
    match = next((c for c in customers if c["name"].lower() == customer_name.lower()), None)
    customer_id = match["id"] if match else db.add_customer(customer_name)
    db.add_transaction(
        customer_id=customer_id,
        amount=amount,
        type=txn_type,
        linked_stock_item_id=linked_stock_item_id,
    )
    return customer_id


def voice_entry_tab():
    st.subheader("\U0001F3A4 Voice Entry")
    st.caption('Speak a transaction, e.g. "Ali ne paanch sau rupay udhaar liya"')

    audio_bytes = audio_recorder(text="Click to record", pause_threshold=2.0)

    if audio_bytes and audio_bytes != st.session_state._last_audio_bytes:
        st.session_state._last_audio_bytes = audio_bytes
        api_key = st.secrets.get("GROQ_API_KEY", "")
        transcript = ""
        parsed = None

        with st.spinner("Transcribing..."):
            try:
                transcript = transcribe_audio(audio_bytes, api_key)
            except Exception as exc:
                st.error(f"Transcription failed: {exc}. You can still enter this manually below.")

        if transcript:
            with st.spinner("Understanding transaction..."):
                try:
                    parsed = extract_transaction(transcript, api_key)
                except Exception as exc:
                    st.error(f"Extraction failed: {exc}. You can still enter this manually below.")

        st.session_state.pending_transcript = transcript
        st.session_state.pending_transaction = parsed

    if st.session_state.pending_transcript:
        st.info(f"**Heard:** {st.session_state.pending_transcript}")
    elif st.session_state._last_audio_bytes is not None:
        st.warning("No speech detected. Please try recording again, or enter the transaction manually below.")

    parsed = st.session_state.pending_transaction or {}
    customers = db.get_customers()
    customer_names = [c["name"] for c in customers]

    st.markdown("#### Confirm before saving")
    st.caption("Nothing is saved until you press Save below — edit anything that looks wrong.")

    with st.form("confirm_txn_form", clear_on_submit=True):
        prefill_name = parsed.get("customer_name") or ""
        name = st.text_input(
            "Customer name",
            value=prefill_name,
            help=f"Existing customers: {', '.join(customer_names)}" if customer_names else None,
        )
        amount = st.number_input(
            "Amount (Rs)",
            min_value=0.0,
            step=10.0,
            value=float(parsed.get("amount") or 0.0),
        )
        default_type = parsed.get("type") if parsed.get("type") in TXN_TYPES else TXN_TYPES[0]
        txn_type = st.selectbox(
            "Transaction type",
            TXN_TYPES,
            index=TXN_TYPES.index(default_type),
            format_func=lambda t: TXN_TYPE_LABELS[t],
        )
        submitted = st.form_submit_button("Save Transaction")

    if submitted:
        if not name.strip() or amount <= 0:
            st.error("Customer name and a positive amount are both required.")
        else:
            _save_transaction(name, amount, txn_type)
            st.session_state.pending_transcript = ""
            st.session_state.pending_transaction = None
            st.success(f"Saved: {name} — Rs {amount:,.2f} ({TXN_TYPE_LABELS[txn_type]})")
            st.rerun()


def ledger_tab():
    st.subheader("\U0001F4D6 Ledger")

    customers = db.get_customers()
    if not customers:
        st.info("No customers yet. Add one below.")
    else:
        st.markdown("##### Customers & Balances")
        for c in sorted(customers, key=lambda x: -x["balance"]):
            balance_label = f"Rs {c['balance']:,.2f} owed" if c["balance"] > 0 else "Settled"
            with st.expander(f"{c['name']} — {balance_label}"):
                txns = db.get_transactions(c["id"])
                if not txns:
                    st.caption("No transactions yet.")
                for t in txns:
                    cols = st.columns([3, 2, 2, 2, 1])
                    cols[0].write(t["date"])
                    cols[1].write(TXN_TYPE_LABELS.get(t["type"], t["type"]))
                    cols[2].write(f"Rs {t['amount']:,.2f}")
                    if cols[3].button("Delete", key=f"del_txn_{t['id']}"):
                        db.delete_transaction(t["id"])
                        st.rerun()

    st.markdown("##### Add Customer")
    with st.form("add_customer_form", clear_on_submit=True):
        new_name = st.text_input("Name")
        new_phone = st.text_input("Phone (optional)")
        if st.form_submit_button("Add Customer") and new_name.strip():
            db.add_customer(new_name.strip(), new_phone.strip() or None)
            st.success(f"Added {new_name}.")
            st.rerun()

    st.markdown("##### Manual Transaction Entry")
    customer_names = [c["name"] for c in db.get_customers()]
    if customer_names:
        with st.form("manual_txn_form", clear_on_submit=True):
            sel_name = st.selectbox("Customer", customer_names)
            amount = st.number_input("Amount (Rs)", min_value=0.0, step=10.0)
            txn_type = st.selectbox("Type", TXN_TYPES, format_func=lambda t: TXN_TYPE_LABELS[t])
            if st.form_submit_button("Add Transaction") and amount > 0:
                _save_transaction(sel_name, amount, txn_type)
                st.success("Transaction added.")
                st.rerun()
    else:
        st.caption("Add a customer first to record a manual transaction.")


def stock_tab():
    st.subheader("\U0001F4E6 Stock")
    dashboard.render_stock_view(DB_PATH)

    st.markdown("##### Add Stock Item")
    with st.form("add_stock_form", clear_on_submit=True):
        item_name = st.text_input("Item name")
        quantity = st.number_input("Quantity", min_value=0, step=1)
        cost_price = st.number_input("Cost price (Rs)", min_value=0.0, step=1.0)
        sale_price = st.number_input("Sale price (Rs)", min_value=0.0, step=1.0)
        threshold = st.number_input("Low stock threshold", min_value=0, step=1, value=5)
        if st.form_submit_button("Add Item") and item_name.strip():
            db.add_stock_item(item_name.strip(), int(quantity), cost_price, sale_price, int(threshold))
            st.success(f"Added {item_name}.")
            st.rerun()

    st.markdown("##### Record a Sale Linked to Stock")
    stock_items = db.get_stock()
    customers = db.get_customers()
    if stock_items and customers:
        with st.form("stock_sale_form", clear_on_submit=True):
            item_names = [s["item_name"] for s in stock_items]
            sel_item = st.selectbox("Item sold", item_names)
            sel_customer = st.selectbox("Customer", [c["name"] for c in customers])
            qty_sold = st.number_input("Quantity sold", min_value=1, step=1, value=1)
            if st.form_submit_button("Record Sale"):
                item = next(s for s in stock_items if s["item_name"] == sel_item)
                total = item["sale_price"] * qty_sold
                _save_transaction(sel_customer, total, "sale", linked_stock_item_id=item["id"])
                db.update_stock_quantity(item["id"], -qty_sold)
                st.success(f"Recorded sale of {qty_sold}x {sel_item} for Rs {total:,.2f}.")
                st.rerun()
    else:
        st.caption("Add at least one stock item and one customer to record a linked sale.")


def main():
    st.set_page_config(page_title="PocketMunshi", page_icon="\U0001F4D2", layout="wide")
    db.init_db(DB_PATH)
    init_state()

    if not st.session_state.authenticated:
        login_gate()
        st.stop()

    with st.sidebar:
        st.title("\U0001F4D2 PocketMunshi")
        if st.button("Log Out"):
            st.session_state.authenticated = False
            st.rerun()
        st.divider()
        if st.button("Backup to CSV"):
            paths = db.export_all_to_csv(CSV_BACKUP_DIR)
            st.success(f"Backed up {len(paths)} tables to {CSV_BACKUP_DIR}/")

    tabs = st.tabs(["Voice Entry", "Ledger", "Stock", "P&L Dashboard", "Reminders"])
    with tabs[0]:
        voice_entry_tab()
    with tabs[1]:
        ledger_tab()
    with tabs[2]:
        stock_tab()
    with tabs[3]:
        dashboard.render_pnl_dashboard(DB_PATH)
    with tabs[4]:
        dashboard.render_reminders_view(DB_PATH)


if __name__ == "__main__":
    main()

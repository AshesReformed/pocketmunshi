# PocketMunshi

A voice-first udhaar (customer credit) ledger for small shopkeepers in Pakistan.
Speak a transaction in Urdu/English code-switched speech — *"Ali ne paanch sau
rupay udhaar liya"* — and PocketMunshi transcribes it, extracts the customer,
amount and type, and lets you confirm before it's saved. Built for a 25-hour
hackathon on a $0 budget.

**Why this exists:** shopkeepers track udhaar in paper notebooks — records get
lost or disputed, there's no P&L visibility, and no systematic stock tracking.
Khatabook/OkCredit proved the market for digitizing this workflow. PocketMunshi's
differentiator is **voice-first entry**, lowering the barrier for low-literacy
or time-pressed shopkeepers who wouldn't otherwise type each transaction.

## Architecture

| File | Owns |
|---|---|
| `db.py` | SQLite data layer — customers, transactions, stock, CSV export |
| `seed_data.py` | Re-runnable demo data (5 customers, ~15-20 transactions, 8 stock items) |
| `voice.py` | Speech-to-text via Groq's hosted `whisper-large-v3-turbo` |
| `extract.py` | Transcript → structured JSON via a Groq-hosted LLM |
| `dashboard.py` | P&L chart, stock view, overdue-reminders view (Streamlit + Plotly) |
| `app.py` | Main app: login gate, voice entry, ledger, stock, navigation |

Every module was unit-tested standalone (see **Testing** below) since each
was built to an interface contract that lets the pieces be verified in
isolation.

## Local setup

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml: set your own shop_username/shop_password,
# and a GROQ_API_KEY from https://console.groq.com (free tier)

python seed_data.py       # populates hisab.db with demo data
streamlit run app.py
```

Log in with whatever `shop_username` / `shop_password` you set in secrets.

## Testing

Every module has a standalone self-test — run these before the demo:

```bash
python test_db.py          # data layer: balances, stock, thresholds, exports
python test_dashboard.py   # P&L computation logic
python test_extract.py                    # defensive JSON-parsing unit tests (no key needed)
python test_extract.py YOUR_GROQ_API_KEY  # REQUIRED before trusting voice entry live
```

**Important — voice accuracy is not yet verified against a real model.** No
Groq API key was available while this was built, so `extract.py`'s prompt has
only been checked for *defensive parsing* (malformed JSON, wrong types), not
real extraction accuracy. `test_extract.py` has 10 realistic sample
transcripts with the correct expected output baked in — run it with a real
key and confirm **at least 8/10 pass** before relying on voice entry for the
demo. If it's below that, treat voice entry as a stretch/demo-only feature
and lean on the manual-entry form (which works standalone regardless).

`app.py`, `dashboard.py`, `voice.py` and `extract.py` were also exercised
end-to-end against stub Streamlit/Groq/Plotly modules to catch integration
bugs (wrong function signatures, crashes on empty state, balance/stock math
across the UI layer) — but that's a substitute for, not a replacement for,
clicking through the real app yourself once dependencies are installed.

## Deploying to Streamlit Community Cloud

1. **Create a public GitHub repo** and push this code:
   ```bash
   git init                     # skip if this folder is already a git repo
   git add -A
   git commit -m "PocketMunshi: voice-first udhaar ledger"
   git remote add origin https://github.com/<your-username>/pocketmunshi.git
   git branch -M main
   git push -u origin main
   ```
   (The repo **must be public** for free Community Cloud hosting.)
   `.streamlit/secrets.toml` is gitignored — only `secrets.toml.example` gets
   committed, so no real credentials leave your machine this way.

2. **Deploy**: go to [share.streamlit.io](https://share.streamlit.io), sign in
   with GitHub, click **"New app"**, pick your `pocketmunshi` repo, branch
   `main`, main file `app.py`, and click **Deploy**. Do this *early* — a live
   "hello world" de-risks deployment problems before you've built on top of it.

3. **Set secrets**: in the app's **Settings → Secrets**, paste the same
   key/value pairs from `secrets.toml.example` with your real values:
   ```toml
   shop_username = "..."
   shop_password = "..."
   GROQ_API_KEY = "..."
   ```

4. **Seed demo data on the deployed app**: Community Cloud's filesystem is
   **not persistent** across app sleep/restarts — a freshly deployed app has
   an empty `hisab.db`. Either:
   - open the deployed app's built-in terminal (if your plan has one) and run
     `python seed_data.py`, or
   - temporarily add a "Reseed demo data" button to the sidebar that calls
     `seed_data.run()`, click it once after each redeploy, then remove it — or
   - run `seed_data.py` locally and commit the resulting `hisab.db` (acceptable
     for a hackathon demo; just know sleep/restart can still wipe it, which is
     exactly why `export_all_to_csv()` exists as a manual safety net — there's
     a "Backup to CSV" button in the app sidebar).

5. **During the demo**: open the app and leave it running rather than
   redeploying right before you present, since a redeploy can wipe the SQLite
   file.

**Live demo URL:** _fill in after deploying —_ `https://<your-app>.streamlit.app`

## Known limitations / next steps

- Voice extraction accuracy is unverified until `test_extract.py <key>` is
  run with a real Groq key (see Testing above) — this is a real go/no-go
  signal, not a detail to bury before the demo.
- P&L profit for a sale **without** a linked stock item counts the full sale
  amount as profit (no cost basis is known) — link sales to stock items where
  possible for accurate numbers.
- SQLite + Streamlit Cloud's ephemeral disk means the ledger can be wiped on
  sleep/restart; `export_all_to_csv()` / the sidebar "Backup to CSV" button is
  the safety net, not automatic backup — export before ending a session if the
  data matters.
- Automated email reminders (`reminder_job.py` + GitHub Actions) were
  explicitly out of scope for this build; `render_reminders_view()` covers the
  required in-app reminders view and works standalone.

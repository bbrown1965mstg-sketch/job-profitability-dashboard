# Job Profitability Dashboard

Local business intelligence dashboard for service jobs — Streamlit + SQLite, dark mode.

## Files

| File | Purpose |
|---|---|
| `generate_sample_data.py` | Writes `sample_jobs.csv` (50 jobs, Aug–Oct 2026, seeded) |
| `ingest.py` | Loads the CSV into `business_intel.db`; derives `labor_cost`, `net_profit`, `profit_margin` in pure SQL |
| `app.py` | Streamlit dashboard (KPIs, job-type breakdown, monthly labor efficiency, top/bottom clients, <15% margin anomaly banner) |

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python generate_sample_data.py   # optional: regenerate the CSV
.venv/bin/python ingest.py                 # (re)build business_intel.db
.venv/bin/streamlit run app.py --server.port 8601
```

Then open http://localhost:8601.

## Notes

- All totals/margins are computed from the database at render time — nothing hardcoded.
- `jobs_raw` keeps the untouched CSV rows; the `jobs` table adds SQL-computed profitability columns.
- Anomaly threshold is `MARGIN_ALERT_PCT` at the top of `app.py` (default 15%).

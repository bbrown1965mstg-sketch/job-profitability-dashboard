"""Ingest sample_jobs.csv into business_intel.db (SQLite).

Raw CSV rows land in the jobs_raw staging table; the jobs table adds
labor_cost, net_profit and profit_margin, all computed by SQL expressions
from the raw columns — no totals are ever hardcoded.
"""
import sqlite3
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
CSV_PATH = HERE / "sample_jobs.csv"
DB_PATH = HERE / "business_intel.db"

COMPUTE_SQL = """
DROP TABLE IF EXISTS jobs;
CREATE TABLE jobs AS
SELECT
    date,
    client_name,
    job_type,
    revenue,
    labor_hours,
    hourly_labor_rate,
    ROUND(labor_hours * hourly_labor_rate, 2) AS labor_cost,
    material_cost,
    overhead_allocation,
    ROUND(revenue
          - (labor_hours * hourly_labor_rate)
          - material_cost
          - overhead_allocation, 2) AS net_profit,
    ROUND(100.0 * (revenue
          - (labor_hours * hourly_labor_rate)
          - material_cost
          - overhead_allocation) / revenue, 2) AS profit_margin
FROM jobs_raw;
CREATE INDEX IF NOT EXISTS idx_jobs_client ON jobs(client_name);
CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(job_type);
"""

SUMMARY_SQL = """
SELECT job_type,
       COUNT(*)                                       AS jobs,
       ROUND(SUM(revenue), 2)                         AS revenue,
       ROUND(SUM(revenue - net_profit), 2)            AS expenses,
       ROUND(SUM(net_profit), 2)                      AS net_profit,
       ROUND(100.0 * SUM(net_profit) / SUM(revenue), 2) AS margin_pct,
       SUM(CASE WHEN profit_margin < 15 THEN 1 ELSE 0 END) AS below_15pct
FROM jobs
GROUP BY job_type
ORDER BY net_profit DESC;
"""


def main() -> None:
    raw = pd.read_csv(CSV_PATH)
    with sqlite3.connect(DB_PATH) as conn:
        raw.to_sql("jobs_raw", conn, if_exists="replace", index=False)
        conn.executescript(COMPUTE_SQL)
        summary = pd.read_sql_query(SUMMARY_SQL, conn)

    print(f"Loaded {len(raw)} rows from {CSV_PATH.name} into {DB_PATH.name}")
    print("\nProfitability by job type (computed in SQL):")
    print(summary.to_string(index=False))
    total = summary["jobs"].sum()
    flagged = summary["below_15pct"].sum()
    print(f"\n{total} jobs ingested, {flagged} flagged below the 15% margin floor.")


if __name__ == "__main__":
    main()

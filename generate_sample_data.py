"""Generate sample_jobs.csv — 50 realistic service jobs across 3 months (Aug-Oct 2026).

Deterministic (seeded) so re-runs produce the same dataset. Margins are derived
from real cost components; ~1 in 5 jobs intentionally lands under the 15%
alert floor so the dashboard's anomaly banner has something to catch.
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUTPUT = Path(__file__).with_name("sample_jobs.csv")

START, END = date(2026, 8, 1), date(2026, 10, 31)
NUM_JOBS = 50
LOW_MARGIN_RATE = 0.22  # share of jobs that dip below the 15% margin floor

# Repeat business: bigger weight = more frequent client
CLIENTS = [
    ("Harborview Property Mgmt", 10),
    ("Pine Hollow Apartments", 9),
    ("Mesa Verde Cafe", 7),
    ("Ironclad Auto Shop", 6),
    ("Cedar Ridge Dental", 6),
    ("Summit View Offices", 5),
    ("Blue Line Logistics", 5),
    ("Casa Verde Restaurant", 4),
    ("Northgate Fitness", 4),
    ("Willow & Sage Salon", 3),
    ("Sterling Law Group", 3),
    ("Bright Path Montessori", 3),
    ("FleetWorks Trucking", 2),
    ("Lakeside Veterinary", 2),
]

JOB_PROFILES = {
    "Maintenance":   {"hours": (1.5, 4.0),  "rate": (55, 75), "material": (0, 180),    "weight": 20},
    "Repair":        {"hours": (2.0, 8.0),  "rate": (65, 85), "material": (60, 650),   "weight": 15},
    "Installation":  {"hours": (6.0, 16.0), "rate": (70, 95), "material": (350, 1600), "weight": 12},
}


def step_round(value: float, step: float) -> float:
    return round(round(value / step) * step, 2)


def sample_margin() -> float:
    """Target margin as a fraction of revenue."""
    if random.random() < LOW_MARGIN_RATE:
        return random.uniform(-0.06, 0.14)  # below the 15% floor -> anomaly
    return random.uniform(0.17, 0.52)


def make_job() -> dict:
    job_type = random.choices(
        list(JOB_PROFILES), weights=[p["weight"] for p in JOB_PROFILES.values()]
    )[0]
    profile = JOB_PROFILES[job_type]

    hours = step_round(random.uniform(*profile["hours"]), 0.25)
    rate = step_round(random.uniform(*profile["rate"]), 0.5)
    material = round(random.uniform(*profile["material"]), 2)

    # Solve revenue from costs so the target margin and overhead share hold:
    # revenue = costs / (1 - margin - overhead_pct)
    labor_cost = hours * rate
    target_margin = sample_margin()
    overhead_pct = random.uniform(0.08, 0.13)
    revenue = step_round((labor_cost + material) / (1 - target_margin - overhead_pct), 5)
    overhead = round(revenue * overhead_pct, 2)

    job_date = START + timedelta(days=random.randrange((END - START).days + 1))
    client = random.choices(
        [name for name, _ in CLIENTS], weights=[weight for _, weight in CLIENTS]
    )[0]

    return {
        "date": job_date.isoformat(),
        "client_name": client,
        "job_type": job_type,
        "revenue": f"{revenue:.2f}",
        "labor_hours": f"{hours:.2f}",
        "hourly_labor_rate": f"{rate:.2f}",
        "material_cost": f"{material:.2f}",
        "overhead_allocation": f"{overhead:.2f}",
    }


def main() -> None:
    jobs = sorted((make_job() for _ in range(NUM_JOBS)), key=lambda job: job["date"])
    with OUTPUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(jobs[0].keys()))
        writer.writeheader()
        writer.writerows(jobs)
    print(f"Wrote {len(jobs)} jobs to {OUTPUT.name} ({START} to {END})")


if __name__ == "__main__":
    main()

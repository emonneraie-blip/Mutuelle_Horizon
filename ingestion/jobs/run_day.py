"""Run every ingestion step for one day, in order (manual demo / debugging; Airflow runs them as separate tasks).

    python -m jobs.run_day --date 2026-10-27 [--simulate-crm]

--simulate-crm first applies that day's CRM activity to Postgres (seed_postgres), as the business application would.
"""
from __future__ import annotations

import argparse
import subprocess
import sys


def step(*args: str) -> None:
    print(f"\n=== python -m {' '.join(args)}", flush=True)
    subprocess.run([sys.executable, "-m", *args], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True)
    ap.add_argument("--simulate-crm", action="store_true")
    a = ap.parse_args()
    if a.simulate_crm:
        step("jobs.seed_postgres", "--date", a.date)
    step("jobs.load_adherents_incremental")
    step("jobs.load_invoices", "--date", a.date)
    step("jobs.load_noemie", "--date", a.date)
    step("jobs.fetch_sirene", "lookup")


if __name__ == "__main__":
    main()

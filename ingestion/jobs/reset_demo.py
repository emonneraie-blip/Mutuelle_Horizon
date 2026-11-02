"""Reset BRONZE and the CRM to replay the demo from scratch (rehearsals, video, plan B).

    python -m jobs.reset_demo --yes                     # keeps the SIRENE / RPPS references (no API calls needed)
    python -m jobs.reset_demo --yes --with-references   # also empties the SIRENE / RPPS tables

Why TRUNCATE and not DELETE: COPY INTO remembers which files were loaded into a table (load metadata, 64 days)
and silently skips them. DELETE removes the rows but keeps that memory, so the same files would never be
reloaded. TRUNCATE TABLE removes the rows AND the load metadata: the same files can be loaded again.

After the reset: seed_postgres --date history, then the history loads and the days (runbook steps 3 to 6),
then dbt build --full-refresh for SILVER / GOLD (owner: transformation).
"""
from __future__ import annotations

import argparse

from .common import get_logger, postgres_conn, snowflake_conn

log = get_logger("reset_demo")

FACT_TABLES = ["FACTURES_OPTIQUE", "NOEMIE_DECOMPTES", "ADHERENTS", "ADHERENTS_STG", "LOAD_AUDIT"]
REF_TABLES = ["SIRENE_ETABLISSEMENTS", "RPPS_PRESCRIPTEURS"]
STAGE_PATHS = ["factures/", "noemie/", "crm/"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="required: confirms that BRONZE and the CRM are emptied")
    ap.add_argument("--with-references", action="store_true", help="also empty the SIRENE / RPPS tables")
    a = ap.parse_args()
    if not a.yes:
        raise SystemExit("Nothing done. Add --yes to empty BRONZE and the CRM.")

    tables = FACT_TABLES + (REF_TABLES if a.with_references else [])
    paths = STAGE_PATHS + (["rpps/"] if a.with_references else [])
    with snowflake_conn() as conn:
        cur = conn.cursor()
        for t in tables:
            cur.execute(f"TRUNCATE TABLE IF EXISTS BRONZE.{t}")      # rows + COPY load metadata
            log.info(f"truncated BRONZE.{t}")
        for p in paths:
            cur.execute(f"REMOVE @BRONZE.LANDING/{p}")              # files already in the stage
            log.info(f"removed stage files @BRONZE.LANDING/{p}")

    with postgres_conn() as pg, pg.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS crm")
        cur.execute("DROP TABLE IF EXISTS crm.adherents")             # seed_postgres recreates it
        pg.commit()
        log.info("CRM table crm.adherents dropped (run seed_postgres --date history next)")
    log.info("reset done")


if __name__ == "__main__":
    main()

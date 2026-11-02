"""Optical claims (CSV, one file per day) -> BRONZE.FACTURES_OPTIQUE.   Method: BATCH file load (PUT + COPY INTO).

    python -m jobs.load_invoices --date 2026-10-27      # one daily batch (what Airflow calls)
    python -m jobs.load_invoices --date history         # the 24-month history
    python -m jobs.load_invoices --all                  # every batch found in DATA_DIR

Idempotent: COPY INTO remembers the files it already loaded (64 days), so a retry or a re-run loads 0 rows.
Schema contract: the header must match EXPECTED_COLUMNS exactly. A new / missing column upstream (schema drift)
stops the job with a clear error *before* anything is loaded: bronze never receives a misaligned file.
"""
from __future__ import annotations

import argparse
import csv

from .common import RAW_DIR, audit, batch_dates, copy_result, get_logger, now, put_file, snowflake_conn

log = get_logger("load_invoices")

EXPECTED_COLUMNS = [
    "id_demande", "canal", "date_reception", "numero_facture", "siret_opticien", "nom_opticien",
    "rpps_prescripteur", "date_prescription", "num_adherent", "nir_beneficiaire", "date_soins", "date_facture",
    "type_equipement", "classe", "categorie_verres", "montant_monture", "montant_verres", "montant_total",
    "base_remboursement_ro", "montant_rembourse_ro", "montant_demande_amc",
]


class SchemaDriftError(Exception):
    pass


def check_header(path) -> int:
    with path.open(encoding="utf-8") as f:
        header = next(csv.reader(f))
        n_rows = sum(1 for _ in f)
    if header != EXPECTED_COLUMNS:
        added = [c for c in header if c not in EXPECTED_COLUMNS]
        missing = [c for c in EXPECTED_COLUMNS if c not in header]
        raise SchemaDriftError(f"{path.name}: header does not match the contract. added={added} missing={missing} "
                               f"order_changed={not added and not missing}")
    return n_rows


def copy_sql(stage_path: str, batch: str) -> str:
    cols = ", ".join(c.upper() for c in EXPECTED_COLUMNS)
    select = ", ".join(f"${i + 1}" for i in range(len(EXPECTED_COLUMNS)))
    batch_expr = "NULL" if batch == "history" else f"'{batch}'::DATE"
    return (f"COPY INTO BRONZE.FACTURES_OPTIQUE ({cols}, _SOURCE_FILE, _FILE_ROW, _BATCH_DATE, _LOADED_AT, _RUN_ID) "
            f"FROM (SELECT {select}, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, {batch_expr}, "
            f"CURRENT_TIMESTAMP(), %s FROM @BRONZE.LANDING/{stage_path}) "
            f"FILE_FORMAT = (FORMAT_NAME = 'BRONZE.FF_CSV') ON_ERROR = 'ABORT_STATEMENT'")


def load_batch(conn, batch: str) -> None:
    from .common import RUN_ID

    started = now()
    files = sorted((RAW_DIR / f"dt={batch}" / "factures").glob("*.csv"))
    if not files:
        log.warning(f"no claim file for batch {batch}")
        audit(conn, "load_invoices", batch, "NO_FILE", started)
        return
    stage_path = f"factures/{batch}/"
    try:
        expected_rows = sum(check_header(p) for p in files)
        cur = conn.cursor()
        for p in files:
            put_file(cur, p, stage_path)
        cur.execute(copy_sql(stage_path, batch), (RUN_ID,))
        n_files, n_rows = copy_result(cur.fetchall())
    except SchemaDriftError as e:
        log.error(str(e))
        audit(conn, "load_invoices", batch, "SCHEMA_DRIFT", started, details={"error": str(e)})
        raise
    status = "LOADED" if n_files else "ALREADY_LOADED"
    log.info(f"batch {batch}: {n_files} file(s), {n_rows} rows loaded ({status}); rows in file(s): {expected_rows}")
    audit(conn, "load_invoices", batch, status, started, n_files, n_rows, {"rows_in_files": expected_rows})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="YYYY-MM-DD or 'history'")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    with snowflake_conn() as conn:
        for batch in batch_dates(a.date, a.all, "factures"):
            load_batch(conn, batch)


if __name__ == "__main__":
    main()

"""Sécurité sociale statements (NOEMIE, JSON lines) -> BRONZE.NOEMIE_DECOMPTES (VARIANT).
Method: BATCH load of semi-structured files (PUT + COPY INTO a VARIANT column).

    python -m jobs.load_noemie --date 2026-10-27
    python -m jobs.load_noemie --all

A missing file is NOT an error here: it is recorded as NO_FILE in BRONZE.LOAD_AUDIT and the job succeeds, so the
other sources are still loaded. The freshness test downstream (dbt source freshness on _LOADED_AT / _BATCH_DATE)
is what raises the incident "NOEMIE flow late" and blocks the fraud rule F2 for that day.
Use --require-file to make the job fail instead.
"""
from __future__ import annotations

import argparse

from .common import RAW_DIR, audit, batch_dates, copy_result, get_logger, now, put_file, snowflake_conn

log = get_logger("load_noemie")


def load_batch(conn, batch: str, require_file: bool) -> None:
    from .common import RUN_ID

    started = now()
    files = sorted((RAW_DIR / f"dt={batch}" / "noemie").glob("*.jsonl"))
    if not files:
        msg = f"no NOEMIE file for batch {batch} (flow late or missing)"
        log.warning(msg)
        audit(conn, "load_noemie", batch, "NO_FILE", started, details={"warning": msg})
        if require_file:
            raise SystemExit(msg)
        return
    expected = sum(sum(1 for line in p.open(encoding="utf-8") if line.strip()) for p in files)
    stage_path = f"noemie/{batch}/"
    cur = conn.cursor()
    for p in files:
        put_file(cur, p, stage_path)
    batch_expr = "NULL" if batch == "history" else f"'{batch}'::DATE"
    cur.execute(
        "COPY INTO BRONZE.NOEMIE_DECOMPTES (RAW, _SOURCE_FILE, _FILE_ROW, _BATCH_DATE, _LOADED_AT, _RUN_ID) "
        f"FROM (SELECT $1, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, {batch_expr}, CURRENT_TIMESTAMP(), %s "
        f"FROM @BRONZE.LANDING/{stage_path}) FILE_FORMAT = (FORMAT_NAME = 'BRONZE.FF_JSON') ON_ERROR = 'ABORT_STATEMENT'",
        (RUN_ID,))
    n_files, n_rows = copy_result(cur.fetchall())
    status = "LOADED" if n_files else "ALREADY_LOADED"
    log.info(f"batch {batch}: {n_files} file(s), {n_rows} statements loaded ({status}); in file(s): {expected}")
    audit(conn, "load_noemie", batch, status, started, n_files, n_rows, {"rows_in_files": expected})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="YYYY-MM-DD or 'history'")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--require-file", action="store_true")
    a = ap.parse_args()
    with snowflake_conn() as conn:
        for batch in batch_dates(a.date, a.all, "noemie"):
            load_batch(conn, batch, a.require_file)


if __name__ == "__main__":
    main()

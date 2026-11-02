"""CRM (Postgres) -> BRONZE.ADHERENTS.   Method: INCREMENTAL pull on a watermark + MERGE (upsert).

    python -m jobs.load_adherents_incremental

1. watermark = MAX(UPDATED_AT) already in BRONZE.ADHERENTS (1900-01-01 on the first run = full load)
2. extract from Postgres only the rows with updated_at >= watermark
   (>= and not >: rows committed with the same timestamp as the watermark are never lost; re-reading them is
    harmless because step 4 is a MERGE)
3. land them as a CSV file in the stage, COPY into BRONZE.ADHERENTS_STG
4. MERGE into BRONZE.ADHERENTS on ID_ADHERENT: update if newer, insert if new.  Re-run = 0 change (idempotent).

Known limits (say them in the defence): a hard DELETE in the CRM is invisible to a watermark, and an update that
does not touch updated_at is missed. Log-based CDC (Debezium, Openflow) would be needed for those cases.
"""
from __future__ import annotations

import csv
import tempfile
from pathlib import Path

from .common import RUN_ID, audit, copy_result, get_logger, now, postgres_conn, put_file, snowflake_conn

log = get_logger("load_adherents_incremental")

COLUMNS = ["ID_ADHERENT", "NIR", "NOM", "PRENOM", "DATE_NAISSANCE", "EMAIL", "TELEPHONE", "CODE_POSTAL", "VILLE",
           "FORMULE", "DATE_DEBUT_CONTRAT", "DATE_FIN_CONTRAT", "STATUT", "UPDATED_AT"]

MERGE = f"""
MERGE INTO BRONZE.ADHERENTS t
USING (
    SELECT * FROM BRONZE.ADHERENTS_STG
    QUALIFY ROW_NUMBER() OVER (PARTITION BY ID_ADHERENT ORDER BY UPDATED_AT DESC) = 1
) s
ON t.ID_ADHERENT = s.ID_ADHERENT
WHEN MATCHED AND s.UPDATED_AT > t.UPDATED_AT THEN UPDATE SET
    {", ".join(f"{c} = s.{c}" for c in COLUMNS[1:])}, _LOADED_AT = CURRENT_TIMESTAMP(), _RUN_ID = %s
WHEN NOT MATCHED THEN INSERT ({", ".join(COLUMNS)}, _LOADED_AT, _RUN_ID)
    VALUES ({", ".join(f"s.{c}" for c in COLUMNS)}, CURRENT_TIMESTAMP(), %s)
"""


def main():
    started = now()
    with snowflake_conn() as sf:
        cur = sf.cursor()
        cur.execute("SELECT COALESCE(MAX(UPDATED_AT), '1900-01-01'::TIMESTAMP_NTZ) FROM BRONZE.ADHERENTS")
        watermark = cur.fetchone()[0]
        log.info(f"watermark = {watermark}")

        with postgres_conn() as pg, pg.cursor() as pcur:
            pcur.execute(f"SELECT {', '.join(c.lower() for c in COLUMNS)} FROM crm.adherents "
                         "WHERE updated_at >= %s ORDER BY updated_at", (watermark,))
            rows = pcur.fetchall()
        log.info(f"{len(rows)} changed row(s) extracted from the CRM")
        if not rows:
            audit(sf, "load_adherents_incremental", None, "NO_CHANGE", started, details={"watermark": str(watermark)})
            return

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"adherents_{RUN_ID}.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
                w.writerow(COLUMNS)
                for r in rows:
                    w.writerow(["" if v is None else (v.isoformat(sep=" ") if hasattr(v, "hour") else v) for v in r])
            cur.execute("TRUNCATE TABLE BRONZE.ADHERENTS_STG")
            stage_path = f"crm/{RUN_ID}/"
            put_file(cur, path, stage_path)
        cur.execute(
            f"COPY INTO BRONZE.ADHERENTS_STG ({', '.join(COLUMNS)}) "
            f"FROM (SELECT {', '.join(f'${i + 1}' for i in range(len(COLUMNS)))} FROM @BRONZE.LANDING/{stage_path}) "
            "FILE_FORMAT = (TYPE = CSV SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '\"' EMPTY_FIELD_AS_NULL = TRUE) "
            "ON_ERROR = 'ABORT_STATEMENT'")
        _, staged = copy_result(cur.fetchall())
        cur.execute(MERGE, (RUN_ID, RUN_ID))
        inserted, updated = cur.fetchone()[:2]
        log.info(f"MERGE: {inserted} inserted, {updated} updated (staged {staged})")
        audit(sf, "load_adherents_incremental", None, "LOADED", started, 1, inserted + updated,
              {"watermark": str(watermark), "extracted": len(rows), "inserted": inserted, "updated": updated})


if __name__ == "__main__":
    main()

"""Shared helpers: configuration from environment, Snowflake (key-pair) and Postgres connections,
JSON logs, run id, audit table. Secrets are only read from the environment / mounted files."""
from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
RAW_DIR = DATA_DIR / "raw"
REF_DIR = DATA_DIR / "ref"
SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
RUN_ID = os.environ.get("RUN_ID") or f"manual-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "level": record.levelname,
                   "job": record.name, "run_id": RUN_ID, "msg": record.getMessage()}
        payload.update(getattr(record, "extra_fields", {}))
        return json.dumps(payload, ensure_ascii=False, default=str)


def get_logger(name: str) -> logging.Logger:
    log = logging.getLogger(name)
    if not log.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(JsonFormatter())
        log.addHandler(h)
        log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    return log


def env(name: str, default: str | None = None) -> str:
    v = os.environ.get(name, default)
    if v is None or v == "":
        raise SystemExit(f"Missing environment variable {name} (see .env.example)")
    return v


# ---------------------------------------------------------------- Snowflake
def snowflake_conn():
    import snowflake.connector
    from cryptography.hazmat.primitives import serialization

    key_path = env("SNOWFLAKE_PRIVATE_KEY_FILE")
    passphrase = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    with open(key_path, "rb") as f:
        pkey = serialization.load_pem_private_key(f.read(), password=passphrase.encode() if passphrase else None)
    der = pkey.private_bytes(encoding=serialization.Encoding.DER, format=serialization.PrivateFormat.PKCS8,
                             encryption_algorithm=serialization.NoEncryption())
    return snowflake.connector.connect(
        account=env("SNOWFLAKE_ACCOUNT"), user=env("SNOWFLAKE_USER"), private_key=der,
        role=env("SNOWFLAKE_ROLE", "INGEST_ROLE"), warehouse=env("SNOWFLAKE_WAREHOUSE", "INGEST_WH"),
        database=env("SNOWFLAKE_DATABASE", "MUTUELLE_FRAUD"), schema="BRONZE",
        session_parameters={"QUERY_TAG": f"fraud-ingest:{RUN_ID}", "TIMEZONE": "Europe/Paris"},
    )


def put_file(cur, local: Path, stage_path: str) -> None:
    """Upload a local file to the internal stage. Re-uploading an identical file is a no-op."""
    cur.execute(f"PUT 'file://{local.resolve().as_posix()}' '@BRONZE.LANDING/{stage_path}' "
                f"AUTO_COMPRESS = TRUE OVERWRITE = FALSE")


def copy_result(rows) -> tuple[int, int]:
    """(files_loaded, rows_loaded) from the result of a COPY INTO."""
    files = loaded = 0
    for r in rows or []:
        if len(r) >= 4 and isinstance(r[3], int):          # file, status, rows_parsed, rows_loaded, ...
            if str(r[1]).upper().startswith("LOADED"):
                files += 1
                loaded += r[3]
    return files, loaded


def audit(conn, job: str, batch: str | None, status: str, started: datetime, files: int = 0, rows: int = 0,
          details: dict | None = None) -> None:
    conn.cursor().execute(
        "INSERT INTO BRONZE.LOAD_AUDIT (RUN_ID, JOB, BATCH_DATE, STATUS, FILES_LOADED, ROWS_LOADED, STARTED_AT, "
        "ENDED_AT, DETAILS) SELECT %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP(), PARSE_JSON(%s)",
        (RUN_ID, job, batch, status, files, rows, started.isoformat(), json.dumps(details or {}, default=str)))


# ---------------------------------------------------------------- Postgres (CRM)
def postgres_conn():
    import psycopg2

    return psycopg2.connect(host=env("PGHOST", "localhost"), port=int(env("PGPORT", "5432")),
                            dbname=env("PGDATABASE", "mutuelle_crm"), user=env("PGUSER", "postgres"),
                            password=os.environ.get("PGPASSWORD", ""), connect_timeout=10)


# ---------------------------------------------------------------- batches
def batch_dates(arg_date: str | None, all_batches: bool, subfolder: str) -> list[str]:
    """'history', a YYYY-MM-DD date, or every batch folder that contains `subfolder`."""
    if all_batches:
        found = sorted(p.parent.name.split("=", 1)[1] for p in RAW_DIR.glob(f"dt=*/{subfolder}"))
        return (["history"] if "history" in found else []) + [d for d in found if d != "history"]
    if not arg_date:
        raise SystemExit("Give --date YYYY-MM-DD, --date history, or --all")
    if arg_date != "history":
        date.fromisoformat(arg_date)
    return [arg_date]


def now() -> datetime:
    return datetime.now(timezone.utc)

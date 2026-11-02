"""Create the BRONZE objects (schema, file formats, stage, tables). Idempotent: safe to run at every deploy.

    python -m jobs.bootstrap_bronze
"""
from __future__ import annotations

from .common import SQL_DIR, get_logger, snowflake_conn

log = get_logger("bootstrap_bronze")


def statements(sql: str):
    lines = [l for l in sql.splitlines() if not l.strip().startswith("--")]
    for stmt in "\n".join(lines).split(";"):
        if stmt.strip():
            yield stmt.strip()


def main():
    sql = (SQL_DIR / "bronze_ddl.sql").read_text(encoding="utf-8")
    with snowflake_conn() as conn:
        cur = conn.cursor()
        for stmt in statements(sql):
            cur.execute(stmt)
            log.info("ok: " + " ".join(stmt.split()[:6]))
    log.info("BRONZE objects ready")


if __name__ == "__main__":
    main()

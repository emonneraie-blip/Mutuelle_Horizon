"""RPPS directory (Annuaire Santé, open data, Licence Ouverte) -> ophthalmologists reference.
Method: BATCH reference load, full refresh (the directory is republished as a whole).

    python -m jobs.load_rpps --extract-only            # download + filter -> DATA_DIR/ref/ophtalmos_rpps.csv
    python -m jobs.load_rpps                           # same, then full refresh of BRONZE.RPPS_PRESCRIPTEURS
    python -m jobs.load_rpps --source-file /data/ref/PS_LibreAcces_Personne_activite.txt   # already downloaded

The source file (PS_LibreAcces_Personne_activite, ~800 MB, '|' separated) is streamed line by line: it is never
held in memory. We keep only ophthalmologists (savoir-faire "Ophtalmologie") and drop names and addresses
(data minimisation): the pipeline only needs to know whether a prescriber RPPS number exists and is an ophthalmologist.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import unicodedata
from pathlib import Path

import requests

from .common import REF_DIR, RUN_ID, audit, copy_result, get_logger, now, put_file, snowflake_conn

log = get_logger("load_rpps")
# data.gouv.fr resource of "Annuaire Santé - Extractions des données en libre accès (RPPS)", file Personne_activite.
# The stable resource URL redirects to the latest monthly extraction. Override with RPPS_URL if it changes.
DEFAULT_URL = "https://www.data.gouv.fr/api/1/datasets/r/fffda7e9-0ea2-4c35-bba0-4496f3af935d"
WANTED = {
    "rpps": ["identifiant pp", "identification nationale pp"],
    "code_profession": ["code profession"],
    "libelle_profession": ["libelle profession"],
    "code_savoir_faire": ["code savoir-faire", "code savoir faire"],
    "libelle_savoir_faire": ["libelle savoir-faire", "libelle savoir faire"],
    "code_postal": ["code postal (coord. structure)", "code postal"],
    "commune": ["libelle commune (coord. structure)", "libelle commune"],
}
OUT_COLUMNS = list(WANTED)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip().strip('"')
    return " ".join(s.replace("’", "'").split())


def column_index(header: list[str]) -> dict[str, int]:
    h = [norm(c) for c in header]
    idx = {}
    for key, names in WANTED.items():
        for name in names:
            if name in h:
                idx[key] = h.index(name)
                break
    missing = [k for k in ("rpps", "libelle_savoir_faire") if k not in idx]
    if missing:
        raise SystemExit(f"RPPS file format changed, columns not found: {missing}. Header was: {header[:25]}")
    return idx


def lines_from(source: str):
    if source.startswith("http"):
        log.info(f"streaming {source}")
        with requests.get(source, stream=True, timeout=60, allow_redirects=True) as r:
            r.raise_for_status()
            r.raw.decode_content = True
            yield from io.TextIOWrapper(r.raw, encoding="utf-8", errors="replace", newline="")
    else:
        with open(source, encoding="utf-8", errors="replace", newline="") as f:
            yield from f


def extract(source: str) -> Path:
    it = lines_from(source)
    header_line = next(it).lstrip("﻿").rstrip("\r\n")
    sep = "|" if header_line.count("|") >= header_line.count(";") else ";"
    idx = column_index(header_line.split(sep))
    keep, seen, scanned = [], set(), 0
    for line in it:
        scanned += 1
        f = line.rstrip("\r\n").split(sep)
        if len(f) <= max(idx.values()):
            continue
        rec = {k: f[i].strip().strip('"') for k, i in idx.items()}
        if "ophtalmolog" not in norm(rec.get("libelle_savoir_faire", "")):
            continue
        if not rec["rpps"] or rec["rpps"] in seen:
            continue
        seen.add(rec["rpps"])
        keep.append(rec)
        if scanned % 500_000 == 0:
            log.info(f"{scanned} lines scanned, {len(keep)} ophthalmologists kept")
    REF_DIR.mkdir(parents=True, exist_ok=True)
    out = REF_DIR / "ophtalmos_rpps.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(keep)
    log.info(f"{scanned} lines scanned, {len(keep)} distinct ophthalmologists -> {out}")
    if len(keep) < 100:
        raise SystemExit("Fewer than 100 ophthalmologists found: wrong file or format change. Nothing loaded.")
    return out


def load(path: Path) -> None:
    started = now()
    with snowflake_conn() as conn:
        cur = conn.cursor()
        stage_path = f"rpps/{RUN_ID}/"
        put_file(cur, path, stage_path)
        cols = ", ".join(c.upper() for c in OUT_COLUMNS)
        select = ", ".join(f"${i + 1}" for i in range(len(OUT_COLUMNS)))
        cur.execute("BEGIN")
        cur.execute("DELETE FROM BRONZE.RPPS_PRESCRIPTEURS")       # full refresh, atomic with the COPY below
        cur.execute(f"COPY INTO BRONZE.RPPS_PRESCRIPTEURS ({cols}, _SOURCE_FILE, _FILE_ROW, _LOADED_AT, _RUN_ID) "
                    f"FROM (SELECT {select}, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, CURRENT_TIMESTAMP(), %s "
                    f"FROM @BRONZE.LANDING/{stage_path}) FILE_FORMAT = (FORMAT_NAME = 'BRONZE.FF_CSV') "
                    f"ON_ERROR = 'ABORT_STATEMENT'", (RUN_ID,))
        files, rows = copy_result(cur.fetchall())
        cur.execute("COMMIT")
        log.info(f"BRONZE.RPPS_PRESCRIPTEURS refreshed: {rows} rows")
        audit(conn, "load_rpps", None, "LOADED", started, files, rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-file", help="local copy of PS_LibreAcces_Personne_activite (skips the download)")
    ap.add_argument("--extract-only", action="store_true", help="only write DATA_DIR/ref/ophtalmos_rpps.csv")
    ap.add_argument("--reuse-extract", action="store_true", help="load the existing ref/ophtalmos_rpps.csv")
    a = ap.parse_args()
    if a.reuse_extract:
        path = REF_DIR / "ophtalmos_rpps.csv"
    else:
        path = extract(a.source_file or os.environ.get("RPPS_URL", DEFAULT_URL))
    if not a.extract_only:
        load(path)


if __name__ == "__main__":
    main()

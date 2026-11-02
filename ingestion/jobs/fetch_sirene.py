"""SIRENE (API Recherche d'entreprises, public, no key) -> opticians reference.   Method: API PULL.

Two modes:

  catalogue   build the list of REAL active optical shops (NAF 47.78A) used by the data generator
              python -m jobs.fetch_sirene catalogue --departements 75 92 93 94 --max 400
              -> DATA_DIR/ref/opticiens_sirene.csv

  lookup      pipeline step: check every SIRET seen in the claims that was not checked yet (incremental)
              python -m jobs.fetch_sirene lookup
              -> BRONZE.SIRENE_ETABLISSEMENTS (raw JSON answer kept in a VARIANT, plus FOUND / ETAT_ADMINISTRATIF)

API hygiene (say it in the defence): timeout on every call, retries with exponential backoff on 429/5xx,
throttling under the published rate limit, loud failure (raise_for_status) on anything else, raw answer kept.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time

import requests

from .common import REF_DIR, RUN_ID, audit, get_logger, now, snowflake_conn

log = get_logger("fetch_sirene")
API = os.environ.get("SIRENE_API_URL", "https://recherche-entreprises.api.gouv.fr/search")
SLEEP = float(os.environ.get("SIRENE_SLEEP_SECONDS", "0.2"))        # stay under the API rate limit
NAF_OPTIQUE = "47.78A"                                                # commerce de détail d'optique


def call(params: dict, retries: int = 4) -> dict:
    for attempt in range(retries + 1):
        try:
            r = requests.get(API, params=params, timeout=15, headers={"User-Agent": "albert-school-student-project"})
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            time.sleep(SLEEP)
            return r.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if attempt == retries or (status is not None and status < 500 and status != 429):
                raise
            wait = 2 ** attempt
            log.warning(f"API error ({e}), retry {attempt + 1}/{retries} in {wait}s")
            time.sleep(wait)
    raise RuntimeError("unreachable")


def establishments(result: dict):
    """Every establishment of a legal unit returned by the API (matching ones first, then the head office)."""
    yield from result.get("matching_etablissements") or []
    if result.get("siege"):
        yield result["siege"]


# ------------------------------------------------------------------ catalogue
def catalogue(departements: list[str], max_rows: int) -> None:
    out, seen = [], set()
    quota = max(1, max_rows // len(departements))          # spread the shops over the departements
    for dep in departements:
        page, start = 1, len(out)
        while len(out) - start < quota:
            data = call({"activite_principale": NAF_OPTIQUE, "departement": dep, "etat_administratif": "A",
                         "per_page": 25, "page": page})
            for res in data.get("results", []):
                for e in establishments(res):
                    siret = e.get("siret")
                    if not siret or siret in seen or e.get("etat_administratif") != "A":
                        continue
                    if (e.get("activite_principale") or NAF_OPTIQUE) != NAF_OPTIQUE:
                        continue
                    seen.add(siret)
                    out.append({"siret": siret, "siren": res.get("siren"),
                                "nom": e.get("nom_commercial") or res.get("nom_complet") or "",
                                "code_postal": e.get("code_postal"), "commune": e.get("libelle_commune") or e.get("commune"),
                                "etat_administratif": e.get("etat_administratif"),
                                "activite_principale": e.get("activite_principale")})
            if page >= int(data.get("total_pages") or 1):
                break
            page += 1
        log.info(f"departement {dep}: {len(out)} opticians so far")
    REF_DIR.mkdir(parents=True, exist_ok=True)
    path = REF_DIR / "opticiens_sirene.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()) if out else ["siret"])
        w.writeheader()
        w.writerows(out[:max_rows])
    log.info(f"{min(len(out), max_rows)} real opticians written to {path}")


# ------------------------------------------------------------------ lookup (pipeline step)
def lookup(max_sirets: int) -> None:
    started = now()
    with snowflake_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT REGEXP_REPLACE(f.SIRET_OPTICIEN, '[^0-9]', '') AS SIRET
            FROM BRONZE.FACTURES_OPTIQUE f
            WHERE LENGTH(REGEXP_REPLACE(f.SIRET_OPTICIEN, '[^0-9]', '')) = 14
              AND REGEXP_REPLACE(f.SIRET_OPTICIEN, '[^0-9]', '') NOT IN (SELECT SIRET FROM BRONZE.SIRENE_ETABLISSEMENTS)
            ORDER BY 1 LIMIT %s""", (max_sirets,))
        sirets = [r[0] for r in cur.fetchall()]
        log.info(f"{len(sirets)} new SIRET(s) to check")
        found_n = 0
        for siret in sirets:
            data = call({"q": siret, "per_page": 5})
            match = None
            for res in data.get("results", []):
                for e in establishments(res):
                    if e.get("siret") == siret:
                        match = {"unite_legale": {k: res.get(k) for k in ("siren", "nom_complet", "etat_administratif",
                                                                         "activite_principale", "date_creation")},
                                 "etablissement": e}
                        break
                if match:
                    break
            found = match is not None
            found_n += found
            etab = (match or {}).get("etablissement", {})
            cur.execute(
                "INSERT INTO BRONZE.SIRENE_ETABLISSEMENTS (SIRET, FOUND, ETAT_ADMINISTRATIF, ACTIVITE_PRINCIPALE, RAW, "
                "_CHECKED_AT, _RUN_ID) SELECT %s, %s, %s, %s, PARSE_JSON(%s), CURRENT_TIMESTAMP(), %s",
                (siret, found, etab.get("etat_administratif"), etab.get("activite_principale"),
                 json.dumps(match or {"answer": "not found", "total_results": data.get("total_results")}), RUN_ID))
        log.info(f"checked {len(sirets)} SIRET(s): {found_n} found, {len(sirets) - found_n} not found")
        audit(conn, "fetch_sirene_lookup", None, "LOADED", started, 0, len(sirets),
              {"found": found_n, "not_found": len(sirets) - found_n})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    c = sub.add_parser("catalogue")
    c.add_argument("--departements", nargs="+", default=["75", "92", "93", "94"])
    c.add_argument("--max", type=int, default=400)
    l_ = sub.add_parser("lookup")
    l_.add_argument("--max", type=int, default=500, help="max SIRETs checked per run")
    a = ap.parse_args()
    if a.mode == "catalogue":
        if any(not re.fullmatch(r"\d[\dAB]", d) for d in a.departements):
            raise SystemExit("departements must look like 75, 2A, 92...")
        catalogue(a.departements, a.max)
    else:
        lookup(a.max)


if __name__ == "__main__":
    main()

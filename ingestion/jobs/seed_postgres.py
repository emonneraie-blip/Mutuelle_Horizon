"""Simulate the CRM application: apply the generated adherent files to the Postgres CRM (crm.adherents).

This is NOT part of the data pipeline: it plays the role of the business application that writes into the
operational database every day. The pipeline then reads this database incrementally (load_adherents_incremental).

    python -m jobs.seed_postgres --date history       # initial snapshot (8,000 adherents)
    python -m jobs.seed_postgres --date 2026-10-27    # the CRM activity of that day (new members, moves, resignations)
    python -m jobs.seed_postgres --all
"""
from __future__ import annotations

import argparse
import csv

from .common import RAW_DIR, batch_dates, get_logger, postgres_conn

log = get_logger("seed_postgres")

DDL = """
CREATE SCHEMA IF NOT EXISTS crm;
CREATE TABLE IF NOT EXISTS crm.adherents (
    id_adherent        VARCHAR(12) PRIMARY KEY,
    nir                VARCHAR(15) NOT NULL,
    nom                VARCHAR(80),
    prenom             VARCHAR(80),
    date_naissance     DATE,
    email              VARCHAR(120),
    telephone          VARCHAR(20),
    code_postal        VARCHAR(5),
    ville              VARCHAR(80),
    formule            VARCHAR(20),
    date_debut_contrat DATE,
    date_fin_contrat   DATE,
    statut             VARCHAR(10),
    updated_at         TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS adherents_updated_at_idx ON crm.adherents (updated_at);
"""

UPSERT = """
INSERT INTO crm.adherents (id_adherent, nir, nom, prenom, date_naissance, email, telephone, code_postal, ville,
                           formule, date_debut_contrat, date_fin_contrat, statut, updated_at)
VALUES (%(id_adherent)s, %(nir)s, %(nom)s, %(prenom)s, %(date_naissance)s, %(email)s, %(telephone)s,
        %(code_postal)s, %(ville)s, %(formule)s, %(date_debut_contrat)s, %(date_fin_contrat)s, %(statut)s,
        %(updated_at)s)
ON CONFLICT (id_adherent) DO UPDATE SET
    nir = EXCLUDED.nir, nom = EXCLUDED.nom, prenom = EXCLUDED.prenom, date_naissance = EXCLUDED.date_naissance,
    email = EXCLUDED.email, telephone = EXCLUDED.telephone, code_postal = EXCLUDED.code_postal,
    ville = EXCLUDED.ville, formule = EXCLUDED.formule, date_debut_contrat = EXCLUDED.date_debut_contrat,
    date_fin_contrat = EXCLUDED.date_fin_contrat, statut = EXCLUDED.statut, updated_at = EXCLUDED.updated_at
WHERE EXCLUDED.updated_at >= crm.adherents.updated_at
"""


def rows(batch: str):
    name = "adherents.csv" if batch == "history" else "adherents_changes.csv"
    with (RAW_DIR / f"dt={batch}" / "crm" / name).open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            yield {k: (v if v != "" else None) for k, v in r.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="YYYY-MM-DD or 'history'")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    with postgres_conn() as conn, conn.cursor() as cur:
        cur.execute(DDL)
        for batch in batch_dates(a.date, a.all, "crm"):
            data = list(rows(batch))
            cur.executemany(UPSERT, data)
            conn.commit()
            log.info(f"CRM batch {batch}: {len(data)} adherent rows upserted")


if __name__ == "__main__":
    main()

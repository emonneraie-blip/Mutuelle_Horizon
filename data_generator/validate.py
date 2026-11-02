#!/usr/bin/env python3
"""Reference implementation of the fraud rules, in plain Python, on the generated files.

Purpose:
  1. prove that every injected fraud is detectable from the sources, after cleaning the mess;
  2. give the transformation owner (dbt, silver/gold) an executable specification of each rule
     and of each cleaning step, with the expected result (recall / precision per rule).

Usage:  python validate.py --data data
Expected: recall 100 % per rule and 0 false positives on the default parameters.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

PLAFONDS = {"SIMPLE": 420.0, "MIXTE": 560.0, "COMPLEXE": 700.0, "TRES_COMPLEXE": 800.0}
GARANTIES = {"ESSENTIEL": 150.0, "CONFORT": 300.0, "PREMIUM": 9999.0}
NULLS = {"", "N/A", "NULL", "-"}


# ---------------- cleaning (what silver must do) ----------------
def clean_text(v):
    v = (v or "").strip()
    return None if v.upper() in NULLS else v


def clean_id(v):
    v = clean_text(v)
    return re.sub(r"\s+", "", v) if v else None


def clean_date(v):
    v = clean_text(v)
    if not v:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            pass
    return None


def clean_amount(v):
    v = clean_text(v)
    if not v:
        return None
    v = v.replace("€", "").replace(" ", "").replace(" ", "")
    if "," in v and "." not in v:
        v = v.replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def clean_code(v):
    v = clean_text(v)
    return v.upper().replace(" ", "_") if v else None


# ---------------- loading ----------------
def read_csv(p: Path):
    with p.open(encoding="utf-8") as f:
        yield from csv.DictReader(f)


def load(data: Path):
    raw = data / "raw"
    invoices, seen_ids, resends = [], set(), 0
    for p in sorted(raw.glob("dt=*/factures/*.csv")):
        for r in read_csv(p):
            if r["id_demande"] in seen_ids:          # technical resend: same claim twice -> keep one
                resends += 1
                continue
            seen_ids.add(r["id_demande"])
            invoices.append({
                "id": r["id_demande"], "history": "history" in p.name,
                "date_reception": clean_date(r["date_reception"]), "numero": clean_text(r["numero_facture"]),
                "siret": clean_id(r["siret_opticien"]), "rpps": clean_id(r["rpps_prescripteur"]),
                "adherent": clean_text(r["num_adherent"]), "nir": clean_id(r["nir_beneficiaire"]),
                "date_soins": clean_date(r["date_soins"]), "classe": clean_code(r["classe"]),
                "categorie": clean_code(r["categorie_verres"]), "amc": clean_amount(r["montant_demande_amc"]),
            })
    noemie = set()
    for p in sorted(raw.glob("dt=*/noemie/*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            d = json.loads(line)
            noemie.add((d["nir"], d["identifiant_ps"], d["date_soins"]))
    crm = {}
    files = [raw / "dt=history" / "crm" / "adherents.csv"] + sorted(raw.glob("dt=20*/crm/adherents_changes.csv"))
    for p in files:
        for r in read_csv(p):
            prev = crm.get(r["id_adherent"])
            if prev is None or r["updated_at"] >= prev["updated_at"]:   # latest version wins (watermark + MERGE)
                crm[r["id_adherent"]] = r
    refs = json.loads((data / "answer_key" / "references_used.json").read_text(encoding="utf-8"))
    return invoices, noemie, crm, refs, resends


# ---------------- rules (what gold must compute) ----------------
def detect(invoices, noemie, crm, refs):
    flags = defaultdict(set)
    known_siret = set(refs["legit_opticiens_siret"])
    known_rpps = set(refs["legit_prescripteurs_rpps"])
    by_adh = defaultdict(list)
    seen_numero = {}
    for inv in sorted(invoices, key=lambda i: (i["date_reception"], i["id"])):
        if inv["history"]:
            by_adh[inv["adherent"]].append(inv["date_soins"])
            seen_numero.setdefault((inv["siret"], inv["numero"]), inv["adherent"])
            continue
        i = inv["id"]
        # F1 renewal < 2 years
        prevs = [d for d in by_adh[inv["adherent"]] if d and inv["date_soins"] and 0 < (inv["date_soins"] - d).days < 730]
        if prevs:
            flags[i].add("F1_RENOUVELLEMENT_PRECOCE")
        by_adh[inv["adherent"]].append(inv["date_soins"])
        # F2 no NOEMIE statement (all files, incl. next-day deliveries)
        if (inv["nir"], inv["siret"], inv["date_soins"].isoformat() if inv["date_soins"] else None) not in noemie:
            flags[i].add("F2_SANS_DECOMPTE_NOEMIE")
        # F3 claimed amount above min(contract ceiling, formula guarantee), classe B only
        adh = crm.get(inv["adherent"], {})
        cap = min(PLAFONDS.get(inv["categorie"], 800.0), GARANTIES.get(adh.get("formule"), 9999.0))
        if inv["classe"] == "B" and inv["amc"] is not None and inv["amc"] > cap + 0.01:
            flags[i].add("F3_MONTANT_GONFLE")
        # F4 optician unknown in SIRENE
        if inv["siret"] not in known_siret:
            flags[i].add("F4_OPTICIEN_FANTOME")
        # F5 invoice number already reimbursed to another adherent
        key = (inv["siret"], inv["numero"])
        if key in seen_numero and seen_numero[key] != inv["adherent"]:
            flags[i].add("F5_FACTURE_REUTILISEE")
        seen_numero.setdefault(key, inv["adherent"])
        # F6 prescriber unknown in RPPS
        if inv["rpps"] not in known_rpps:
            flags[i].add("F6_PRESCRIPTEUR_INVALIDE")
        # F7 care after contract end
        fin = clean_date(adh.get("date_fin_contrat"))
        if fin and inv["date_soins"] and inv["date_soins"] > fin:
            flags[i].add("F7_ADHERENT_RESILIE")
    return flags


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data")
    a = p.parse_args()
    data = Path(a.data)
    invoices, noemie, crm, refs, resends = load(data)
    flags = detect(invoices, noemie, crm, refs)
    truth = {r["id_demande"]: r["fraud_type"] for r in read_csv(data / "answer_key" / "fraud_answer_key.csv")}
    unparsed = sum(1 for i in invoices if not i["date_soins"] or i["amc"] is None)
    print(f"claims (deduplicated): {len(invoices)} | technical resends removed: {resends} | unparsable rows: {unparsed}")
    print(f"{'rule':30} {'injected':>8} {'found':>6} {'recall':>7}")
    ok = True
    for t in sorted(set(truth.values())):
        ids = [i for i, v in truth.items() if v == t]
        found = sum(1 for i in ids if t in flags.get(i, set()))
        ok &= found == len(ids)
        print(f"{t:30} {len(ids):8} {found:6} {found / len(ids):7.0%}")
    false_pos = [i for i in flags if i not in truth]
    multi = [i for i in flags if i in truth and len(flags[i]) > 1]
    print(f"false positives: {len(false_pos)} {false_pos[:5]}")
    print(f"frauds flagged by more than one rule: {len(multi)}")
    if not ok or false_pos:
        raise SystemExit("VALIDATION FAILED")
    print("VALIDATION OK")


if __name__ == "__main__":
    main()

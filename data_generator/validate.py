#!/usr/bin/env python3
"""Reference implementation of the fraud rules, in plain Python, on the generated files.

Purpose:
  1. prove that every injected fraud is detectable from the sources, after cleaning the mess;
  2. give the transformation owner (dbt, silver/gold) an EXECUTABLE SPECIFICATION of each cleaning step,
     of the quarantine and of each rule, with the expected result.

It simulates the pipeline as it runs on the morning that processes batch AS_OF: only the files received up to
AS_OF are visible (claims, NOEMIE, CRM changes), exactly like in Snowflake.

Usage:
  python validate.py --data data                        # as of the last batch (default)
  python validate.py --data data --as-of 2026-10-31     # as of one morning
  python validate.py --data data --each-day             # every morning of the period (what the dashboard shows)

Rules of the game (same in dbt):
  - quarantine: date_reception or date_soins unparsable, montant_demande_amc missing, or a negative amount
    -> the claim goes to slv_factures_quarantaine and is excluded from every rule and from the history;
  - F2 is evaluated only when date_reception <= AS_OF - 2 days (a statement can arrive up to 2 days late);
    before that, F2 is "EN_ATTENTE" (pending), the other six rules apply immediately;
  - acceptance: 100 % recall on every evaluable rule, 0 false positive, every morning; at least --min-per-rule
    evaluable frauds per rule and one F5 on the last day.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

PLAFONDS = {"SIMPLE": 420.0, "MIXTE": 560.0, "COMPLEXE": 700.0, "TRES_COMPLEXE": 800.0}
GARANTIES = {"ESSENTIEL": 150.0, "CONFORT": 300.0, "PREMIUM": 9999.0}
NULLS = {"", "N/A", "NULL", "-"}
F2 = "F2_SANS_DECOMPTE_NOEMIE"
F2_GRACE_DAYS = 2
RULES = ["F1_RENOUVELLEMENT_PRECOCE", F2, "F3_MONTANT_GONFLE", "F4_OPTICIEN_FANTOME", "F5_FACTURE_REUTILISEE",
         "F6_PRESCRIPTEUR_INVALIDE", "F7_ADHERENT_RESILIE"]


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
    v = v.replace("€", "").replace(" ", "").replace(" ", "")
    if "," in v and "." not in v:
        v = v.replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def clean_code(v):
    v = clean_text(v)
    return v.upper().replace(" ", "_") if v else None


def quarantine_reason(inv):
    if inv["date_reception"] is None:
        return "DATE_RECEPTION_INVALIDE"
    if inv["date_soins"] is None:
        return "DATE_SOINS_INVALIDE"
    if inv["amc"] is None:
        return "MONTANT_MANQUANT"
    if inv["amc"] < 0 or (inv["total"] is not None and inv["total"] < 0):
        return "MONTANT_NEGATIF"
    return None


# ---------------- loading: only what has been received by AS_OF ----------------
def read_csv(p: Path):
    with p.open(encoding="utf-8") as f:
        yield from csv.DictReader(f)


def received(raw: Path, pattern: str, as_of: date, with_history: bool = True):
    """Files of the batches received up to AS_OF (dt=history first, then dt=YYYY-MM-DD in order)."""
    out = []
    for p in sorted(raw.glob(pattern)):
        part = p.relative_to(raw).parts[0][3:]          # 'history' or 'YYYY-MM-DD'
        if part == "history":
            if with_history:
                out.insert(0, p)
        elif date.fromisoformat(part) <= as_of:
            out.append(p)
    return out


def load(data: Path, as_of: date):
    raw = data / "raw"
    invoices, quarantined, seen_ids, resends = [], {}, set(), 0
    for p in received(raw, "dt=*/factures/*.csv", as_of):
        for r in read_csv(p):
            if r["id_demande"] in seen_ids:          # technical resend: same claim twice -> keep one
                resends += 1
                continue
            seen_ids.add(r["id_demande"])
            inv = {
                "id": r["id_demande"], "history": "history" in p.name,
                "date_reception": clean_date(r["date_reception"]), "numero": clean_text(r["numero_facture"]),
                "siret": clean_id(r["siret_opticien"]), "rpps": clean_id(r["rpps_prescripteur"]),
                "adherent": clean_text(r["num_adherent"]), "nir": clean_id(r["nir_beneficiaire"]),
                "date_soins": clean_date(r["date_soins"]), "classe": clean_code(r["classe"]),
                "categorie": clean_code(r["categorie_verres"]), "amc": clean_amount(r["montant_demande_amc"]),
                "total": clean_amount(r["montant_total"]),
            }
            reason = quarantine_reason(inv)
            if reason:
                quarantined[inv["id"]] = reason
            else:
                invoices.append(inv)
    noemie = set()
    for p in received(raw, "dt=*/noemie/*.jsonl", as_of):
        for line in p.read_text(encoding="utf-8").splitlines():
            d = json.loads(line)
            noemie.add((d["nir"], d["identifiant_ps"], d["date_soins"]))
    crm = {}
    for p in received(raw, "dt=*/crm/*.csv", as_of):
        for r in read_csv(p):
            prev = crm.get(r["id_adherent"])
            if prev is None or r["updated_at"] >= prev["updated_at"]:   # latest version wins (watermark + MERGE)
                crm[r["id_adherent"]] = r
    refs = json.loads((data / "answer_key" / "references_used.json").read_text(encoding="utf-8"))
    return invoices, quarantined, noemie, crm, refs, resends


# ---------------- rules (what gold must compute) ----------------
def detect(invoices, noemie, crm, refs, as_of: date):
    flags, f2_pending = defaultdict(set), set()
    f2_limit = as_of - timedelta(days=F2_GRACE_DAYS)
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
        # F1 renewal < 2 years (previous non-quarantined equipment of the same adherent)
        if any(0 < (inv["date_soins"] - d).days < 730 for d in by_adh[inv["adherent"]] if d):
            flags[i].add("F1_RENOUVELLEMENT_PRECOCE")
        by_adh[inv["adherent"]].append(inv["date_soins"])
        # F2 no NOEMIE statement received (nir, siret, date_soins) -- only after the grace period
        if inv["date_reception"] > f2_limit:
            f2_pending.add(i)
        elif (inv["nir"], inv["siret"], inv["date_soins"].isoformat()) not in noemie:
            flags[i].add(F2)
        # F3 claimed amount above min(contract ceiling, formula guarantee), classe B only
        adh = crm.get(inv["adherent"], {})
        cap = min(PLAFONDS.get(inv["categorie"], 800.0), GARANTIES.get(adh.get("formule"), 9999.0))
        if inv["classe"] == "B" and inv["amc"] > cap + 0.01:
            flags[i].add("F3_MONTANT_GONFLE")
        # F4 optician unknown (or closed) in SIRENE
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
        if fin and inv["date_soins"] > fin:
            flags[i].add("F7_ADHERENT_RESILIE")
    return flags, f2_pending


# ---------------- one morning ----------------
def evaluate(data: Path, as_of: date, verbose: bool):
    invoices, quarantined, noemie, crm, refs, resends = load(data, as_of)
    flags, f2_pending = detect(invoices, noemie, crm, refs, as_of)
    truth = {r["id_demande"]: r for r in read_csv(data / "answer_key" / "fraud_answer_key.csv")
             if date.fromisoformat(r["date_reception"]) <= as_of}
    expected_q = {r["id_demande"]: r["reason"] for r in read_csv(data / "answer_key" / "quarantine_key.csv")
                  if date.fromisoformat(r["date_reception"]) <= as_of}
    problems, stats = [], {}
    for t in RULES:
        ids = [i for i, r in truth.items() if r["fraud_type"] == t]
        pending = [i for i in ids if t == F2 and i in f2_pending]
        evaluable = [i for i in ids if i not in pending]
        found = sum(1 for i in evaluable if t in flags.get(i, set()))
        stats[t] = (len(ids), len(pending), len(evaluable), found)
        if found < len(evaluable):
            problems.append(f"{t}: {found}/{len(evaluable)} found")
    false_pos = sorted(i for i in flags if i not in truth)
    if false_pos:
        problems.append(f"{len(false_pos)} false positive(s) {false_pos[:5]}")
    if set(quarantined) != set(expected_q):
        problems.append(f"quarantine mismatch: {len(quarantined)} found vs {len(expected_q)} expected")
    if verbose:
        daily = sum(1 for i in invoices if not i["history"] and i["date_reception"] and i["date_reception"] > date.min)
        print(f"as of {as_of} | claims kept: {daily} | technical resends removed: {resends} | "
              f"quarantined: {len(quarantined)} {dict(sorted(_count(quarantined.values()).items()))}")
        print(f"{'rule':28} {'injected':>8} {'F2 pending':>10} {'evaluable':>9} {'found':>6} {'recall':>7}")
        for t, (n, pend, ev, found) in stats.items():
            rec = f"{found / ev:7.0%}" if ev else "    n/a"
            print(f"{t:28} {n:8} {pend:10} {ev:9} {found:6} {rec}")
        print(f"false positives: {len(false_pos)} | claims with F2 pending: {len(f2_pending)} | "
              f"frauds flagged by more than one rule: {sum(1 for i in flags if i in truth and len(flags[i]) > 1)}")
    return problems, stats, truth


def _count(values):
    out = defaultdict(int)
    for v in values:
        out[v] += 1
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", default="data")
    p.add_argument("--as-of", help="batch date processed that morning (default: last batch of the data set)")
    p.add_argument("--each-day", action="store_true", help="check every morning of the period")
    p.add_argument("--min-per-rule", type=int, default=5)
    a = p.parse_args()
    data = Path(a.data)
    manifest = json.loads((data / "answer_key" / "generation_manifest.json").read_text(encoding="utf-8"))
    first, last = date.fromisoformat(manifest["first_day"]), date.fromisoformat(manifest["last_day"])
    as_of = date.fromisoformat(a.as_of) if a.as_of else last

    problems = []
    if a.each_day:
        d = first
        while d <= last:
            day_problems, _, _ = evaluate(data, d, verbose=False)
            print(f"morning of {d + timedelta(days=1)} (batch {d}): {'OK' if not day_problems else day_problems}")
            problems += [f"{d}: {x}" for x in day_problems]
            d += timedelta(days=1)
        print()
    day_problems, stats, truth = evaluate(data, as_of, verbose=True)
    problems += day_problems

    if as_of >= last:                                   # data-set guarantees, on the full period
        short = {t: s[2] for t, s in stats.items() if s[2] < a.min_per_rule}
        if short:
            problems.append(f"fewer than {a.min_per_rule} evaluable frauds for {short}")
        f5_last = [i for i, r in truth.items() if r["fraud_type"] == "F5_FACTURE_REUTILISEE"
                   and r["date_reception"] == last.isoformat()]
        if not f5_last:
            problems.append(f"no F5 on the last day {last} (needed for the live demo)")
        else:
            print(f"F5 to open in the live demo ({last}): {f5_last}")
    print(f"synthetic references: {manifest.get('synthetic_references')}")
    if problems:
        for x in problems:
            print("  -", x)
        raise SystemExit("VALIDATION FAILED")
    print("VALIDATION OK")


if __name__ == "__main__":
    main()

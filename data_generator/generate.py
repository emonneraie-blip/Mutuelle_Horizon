#!/usr/bin/env python3
"""Mutuelle Horizon Santé · synthetic optical-claims generator (fraud detection project).

Produces realistic, deliberately *messy* source data for a fictional French complementary
health insurer (mutuelle), with fraud cases injected on purpose and an answer key.

Standard library only (Python 3.9+). Same --seed = exactly the same files.

Outputs (default --out data):
  data/raw/dt=history/factures/factures_optique_history.csv   24 months of paid claims (clean, no fraud)
  data/raw/dt=history/noemie/noemie_history.jsonl              matching Sécurité sociale statements
  data/raw/dt=history/crm/adherents.csv                        initial CRM snapshot (load into Postgres)
  data/raw/dt=YYYY-MM-DD/factures/factures_optique_YYYYMMDD.csv  claims received that day (messy)
  data/raw/dt=YYYY-MM-DD/noemie/noemie_YYYYMMDD.jsonl            NOEMIE statements received that day
  data/raw/dt=YYYY-MM-DD/crm/adherents_changes.csv               CRM inserts/updates of that day
  data/answer_key/fraud_answer_key.csv                         one line per injected fraud
  data/answer_key/quarantine_key.csv                           legit claims made unusable on purpose (silver quarantine)
  data/answer_key/noise_report.json                            every kind of mess injected, with counts
  data/answer_key/generation_manifest.json                     parameters + seed (put it in the README)
  data/ref/                                                    copy of the reference files used (for load_rpps --reuse-extract)

Reference data (required): real opticians from the SIRENE API and real ophthalmologists from the
RPPS directory, FROZEN in data_generator/ref/ (no names) so that the same seed gives the same files on
every machine. They are produced once by the ingestion jobs (`fetch_sirene catalogue`,
`load_rpps --extract-only`). Without them the generator stops, unless --allow-synthetic (CI only:
synthetic SIRET/RPPS numbers, the SIRENE rule is then meaningless against the real API).

Guarantees (checked again by validate.py): at least --min-per-rule frauds for each rule F1..F7 (F2 counted
outside the grace period), at least one F5 on the last day (opened during the live demo), and one
invalid legit claim per day (negative amount or impossible date) for the silver quarantine.

Ethics: every person is fictitious. Real SIRET numbers are only used on *legitimate* claims or as
the letterhead forged by a fictitious adherent, and the optician NAME is always fictitious:
no real optician is ever displayed next to a fraud.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import shutil
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

# --------------------------------------------------------------------------------------
# Business constants (simplified, documented in docs/contracts.md)
# --------------------------------------------------------------------------------------
# Contrat responsable ceilings for a "classe B" equipment (frame included, frame <= 100 EUR)
PLAFONDS = {"SIMPLE": 420.0, "MIXTE": 560.0, "COMPLEXE": 700.0, "TRES_COMPLEXE": 800.0}
# What each formula pays on optics (classe B), capped by the contract ceiling
GARANTIES = {"ESSENTIEL": 150.0, "CONFORT": 300.0, "PREMIUM": 9999.0}
FORMULES = [("ESSENTIEL", 0.45), ("CONFORT", 0.40), ("PREMIUM", 0.15)]
CATEGORIES = [("SIMPLE", 0.55), ("MIXTE", 0.15), ("COMPLEXE", 0.22), ("TRES_COMPLEXE", 0.08)]
# typical price ranges of a full classe B equipment, by lens category
PRIX_B = {"SIMPLE": (180, 420), "MIXTE": (300, 560), "COMPLEXE": (380, 700), "TRES_COMPLEXE": (450, 800)}
PRIX_A = (90, 190)            # 100% Santé (classe A) equipment
CODE_LPP = {"SIMPLE": "2203240", "MIXTE": "2263459", "COMPLEXE": "2235776", "TRES_COMPLEXE": "2259966"}  # illustrative
RENOUVELLEMENT_JOURS = 730    # adults: 1 equipment every 2 years
F2_GRACE_DAYS = 2             # a NOEMIE statement can arrive up to 2 days after the claim (late file incident)
REF_DIR_DEFAULT = Path(__file__).resolve().parent / "ref"     # frozen reference extracts, versioned in Git

FRAUD_TYPES = {
    "F1_RENOUVELLEMENT_PRECOCE": "Second full equipment less than 2 years after the previous one (adult)",
    "F2_SANS_DECOMPTE_NOEMIE": "Invoice never matched by a Sécurité sociale statement (fake invoice)",
    "F3_MONTANT_GONFLE": "Amount inflated: claimed mutuelle part above the contract ceiling and the formula",
    "F4_OPTICIEN_FANTOME": "SIRET of an optician that does not exist in SIRENE",
    "F5_FACTURE_REUTILISEE": "Same optician invoice number already reimbursed for another adherent",
    "F6_PRESCRIPTEUR_INVALIDE": "Prescriber RPPS number unknown in the RPPS directory",
    "F7_ADHERENT_RESILIE": "Care date after the end of the adherent's contract",
}
FRAUD_MIX = [("F1_RENOUVELLEMENT_PRECOCE", 0.15), ("F2_SANS_DECOMPTE_NOEMIE", 0.25), ("F3_MONTANT_GONFLE", 0.20),
             ("F4_OPTICIEN_FANTOME", 0.10), ("F5_FACTURE_REUTILISEE", 0.10), ("F6_PRESCRIPTEUR_INVALIDE", 0.10),
             ("F7_ADHERENT_RESILIE", 0.10)]

INVOICE_COLUMNS = [
    "id_demande", "canal", "date_reception", "numero_facture", "siret_opticien", "nom_opticien",
    "rpps_prescripteur", "date_prescription", "num_adherent", "nir_beneficiaire", "date_soins", "date_facture",
    "type_equipement", "classe", "categorie_verres", "montant_monture", "montant_verres", "montant_total",
    "base_remboursement_ro", "montant_rembourse_ro", "montant_demande_amc",
]
CRM_COLUMNS = ["id_adherent", "nir", "nom", "prenom", "date_naissance", "email", "telephone", "code_postal",
               "ville", "formule", "date_debut_contrat", "date_fin_contrat", "statut", "updated_at"]

PRENOMS = ["Camille", "Léa", "Manon", "Chloé", "Inès", "Sarah", "Emma", "Jade", "Louise", "Alice", "Lucas",
           "Hugo", "Louis", "Gabriel", "Arthur", "Jules", "Adam", "Raphaël", "Nathan", "Thomas", "Hélène",
           "François", "Zoé", "Noé", "Maël", "Anaïs", "Jérôme", "Céline", "Yasmine", "Mohamed", "Karim", "Lina"]
NOMS = ["Martin", "Bernard", "Dubois", "Thomas", "Robert", "Richard", "Petit", "Durand", "Leroy", "Moreau",
        "Simon", "Laurent", "Lefèvre", "Michel", "Garcia", "David", "Bertrand", "Roux", "Vincent", "Fournier",
        "Morel", "Girard", "André", "Mercier", "Dupont", "Lambert", "Bonnet", "François", "Martinez", "Nguyen"]
VILLES = [("75011", "Paris"), ("75015", "Paris"), ("75018", "Paris"), ("92100", "Boulogne-Billancourt"),
          ("92300", "Levallois-Perret"), ("93100", "Montreuil"), ("94300", "Vincennes"), ("69003", "Lyon"),
          ("13008", "Marseille"), ("33000", "Bordeaux"), ("59000", "Lille"), ("31000", "Toulouse"),
          ("44000", "Nantes"), ("67000", "Strasbourg"), ("06000", "Nice"), ("35000", "Rennes")]
OPTIQUE_NOMS = ["Optique", "Vision", "Lunetterie", "Opticiens", "Regard", "Optic"]
OPTIQUE_SUFFIX = ["du Centre", "de la Gare", "Saint-Michel", "Bastille", "des Halles", "Voltaire", "Lumière",
                  "Horizon", "Clair", "Plus", "Concept", "& Co"]


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def weighted(rng: random.Random, pairs):
    values, weights = zip(*pairs)
    return rng.choices(values, weights=weights, k=1)[0]


def luhn_complete(digits: str) -> str:
    """Append the Luhn check digit (SIREN/SIRET use the Luhn algorithm)."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return digits + str((10 - total % 10) % 10)


def fake_siret(rng: random.Random) -> str:
    return luhn_complete("".join(str(rng.randint(0, 9)) for _ in range(13)))


def fake_rpps(rng: random.Random) -> str:
    return "10" + "".join(str(rng.randint(0, 9)) for _ in range(9))


def fake_nir(rng: random.Random, sexe: int, naissance: date, dept: str) -> str:
    body = f"{sexe}{naissance.year % 100:02d}{naissance.month:02d}{dept[:2]}{rng.randint(1, 999):03d}{rng.randint(1, 999):03d}"
    key = 97 - (int(body) % 97)
    return f"{body}{key:02d}"


def money(x: float) -> float:
    return round(x + 1e-9, 2)


# --------------------------------------------------------------------------------------
# Mess (noise) applied to the text written in files. The answer key is computed on clean values.
# --------------------------------------------------------------------------------------
class Mess:
    LEVELS = {"low": 0.01, "medium": 0.04, "high": 0.10}

    def __init__(self, rng: random.Random, level: str):
        self.rng, self.p, self.report = rng, self.LEVELS[level], {}

    def _hit(self, kind: str) -> bool:
        if self.rng.random() < self.p:
            self.report[kind] = self.report.get(kind, 0) + 1
            return True
        return False

    def date(self, d: date | None) -> str:
        if d is None:
            return ""
        if self._hit("date_format_dd_mm_yyyy"):
            return d.strftime("%d/%m/%Y")
        if self._hit("date_format_yyyymmdd"):
            return d.strftime("%Y%m%d")
        return d.isoformat()

    def amount(self, x: float) -> str:
        if self._hit("amount_decimal_comma"):
            return f"{x:.2f}".replace(".", ",")
        if self._hit("amount_with_euro_sign"):
            return f"{x:,.2f} €".replace(",", " ").replace(".", ",")
        return f"{x:.2f}"

    def code(self, v: str) -> str:
        if self._hit("category_case_spaces"):
            return self.rng.choice([v.lower(), f" {v} ", v.title()])
        return v

    def ident(self, v: str, kind: str) -> str:
        if self._hit(f"{kind}_with_spaces"):
            return " ".join(v[i:i + 3] for i in range(0, len(v), 3))
        return v

    def optional(self, v: str, kind: str) -> str:
        if self._hit(f"{kind}_missing"):
            return self.rng.choice(["", "N/A", "null", "-"])
        return v

    def name(self, v: str) -> str:
        if self._hit("name_case"):
            return v.upper()
        return v


# --------------------------------------------------------------------------------------
# Generator
# --------------------------------------------------------------------------------------
class Generator:
    def __init__(self, args):
        self.a = args
        self.rng = random.Random(args.seed)
        self.mess = Mess(random.Random(args.seed + 1), args.mess)
        self.out = Path(args.out)
        self.start = date.fromisoformat(args.start_date)
        self.days = [self.start + timedelta(days=i) for i in range(args.days)]
        self.answer_key: list[dict] = []
        self.quarantine_key: list[dict] = []
        self.noise_rows: list[dict] = []
        self.invoice_seq = 0
        self.synthetic_refs = {"opticiens": False, "prescripteurs": False}

    # ---------------- reference data ----------------
    def fake_name(self) -> str:
        return f"{self.rng.choice(OPTIQUE_NOMS)} {self.rng.choice(OPTIQUE_SUFFIX)}"

    def load_refs(self):
        ref = Path(self.a.refs_dir)
        self.opticiens = []
        p = ref / "opticiens_sirene.csv"
        if p.exists():
            with p.open(encoding="utf-8") as f:
                sirets = sorted({r["siret"].strip() for r in csv.DictReader(f)
                                 if r.get("siret") and r.get("etat_administratif", "A") == "A"})
            self.rng.shuffle(sirets)
            # real SIRET (checked against the real SIRENE API by the pipeline), FICTITIOUS name (ethics)
            self.opticiens = [{"siret": s, "nom": self.fake_name()} for s in sirets[: self.a.opticiens]]
        if len(self.opticiens) < 10:
            self.synthetic_refs["opticiens"] = True
            self.opticiens = [{"siret": fake_siret(self.rng), "nom": self.fake_name()} for _ in range(self.a.opticiens)]
        self.ghosts = [{"siret": fake_siret(self.rng), "nom": self.fake_name()} for _ in range(6)]

        self.prescripteurs = []
        p = ref / "ophtalmos_rpps.csv"
        if p.exists():
            with p.open(encoding="utf-8") as f:
                self.prescripteurs = [r["rpps"].strip() for r in csv.DictReader(f) if r.get("rpps")]
            self.rng.shuffle(self.prescripteurs)
            self.prescripteurs = self.prescripteurs[: self.a.prescripteurs]
        if len(self.prescripteurs) < 10:
            self.synthetic_refs["prescripteurs"] = True
            self.prescripteurs = [fake_rpps(self.rng) for _ in range(self.a.prescripteurs)]
        if any(self.synthetic_refs.values()) and not self.a.allow_synthetic:
            raise SystemExit(f"Reference files missing or too small in {ref} ({self.synthetic_refs}). "
                             "Freeze the real SIRENE / RPPS extracts first (see docs/part1_sources_bronze.md), "
                             "or pass --allow-synthetic (CI only).")
        for name in ("opticiens_sirene.csv", "ophtalmos_rpps.csv"):      # copy for load_rpps --reuse-extract
            if (ref / name).exists():
                (self.out / "ref").mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ref / name, self.out / "ref" / name)
        known = set(self.prescripteurs)
        self.fake_prescripteurs = []
        while len(self.fake_prescripteurs) < 15:
            r = fake_rpps(self.rng)
            if r not in known:
                self.fake_prescripteurs.append(r)

    # ---------------- CRM ----------------
    def make_adherent(self, i: int, joined_before: date) -> dict:
        rng = self.rng
        sexe = rng.choice([1, 2])
        naissance = date(rng.randint(1945, 2005), rng.randint(1, 12), rng.randint(1, 28))
        cp, ville = rng.choice(VILLES)
        prenom, nom = rng.choice(PRENOMS), rng.choice(NOMS)
        debut = joined_before - timedelta(days=rng.randint(30, 3650))
        return {
            "id_adherent": f"ADH{i:07d}", "nir": fake_nir(rng, sexe, naissance, cp), "nom": nom, "prenom": prenom,
            "date_naissance": naissance, "email": f"{prenom}.{nom}{rng.randint(1, 99)}@example.fr".lower(),
            "telephone": f"06{rng.randint(10000000, 99999999)}", "code_postal": cp, "ville": ville,
            "formule": weighted(rng, FORMULES), "date_debut_contrat": debut, "date_fin_contrat": None,
            "statut": "ACTIF", "updated_at": datetime.combine(debut, time(9, 0)),
        }

    def crm_row(self, a: dict) -> dict:
        m = self.mess
        return {
            "id_adherent": a["id_adherent"], "nir": a["nir"], "nom": m.name(a["nom"]), "prenom": a["prenom"],
            "date_naissance": a["date_naissance"].isoformat(), "email": m.optional(a["email"], "email"),
            "telephone": a["telephone"], "code_postal": a["code_postal"], "ville": a["ville"],
            "formule": a["formule"], "date_debut_contrat": a["date_debut_contrat"].isoformat(),
            "date_fin_contrat": a["date_fin_contrat"].isoformat() if a["date_fin_contrat"] else "",
            "statut": a["statut"], "updated_at": a["updated_at"].isoformat(sep=" "),
        }

    # ---------------- claims ----------------
    def new_id(self, d: date) -> str:
        self.invoice_seq += 1
        return f"DEM{d:%Y%m%d}{self.invoice_seq:07d}"

    def build_claim(self, adh: dict, d_soins: date, d_recep: date, opt: dict, rpps: str, canal: str) -> dict:
        rng = self.rng
        classe = "A" if rng.random() < 0.18 else "B"
        cat = weighted(rng, CATEGORIES)
        if classe == "A":
            total = money(rng.uniform(*PRIX_A))
            monture = money(min(30.0, total * 0.25))
            base = total
            ro = money(total * 0.60)
            amc = money(total - ro)
        else:
            total = money(rng.uniform(*PRIX_B[cat]))
            monture = money(min(rng.uniform(40, 100), total * 0.4))
            base = 0.10
            ro = 0.06
            cap = min(PLAFONDS[cat], GARANTIES[adh["formule"]])
            amc = money(min(total - ro, cap))
        d_presc = d_soins - timedelta(days=rng.randint(5, 300))
        return {
            "id_demande": self.new_id(d_recep), "canal": canal, "date_reception": d_recep,
            "numero_facture": f"F{d_soins.year}-{rng.randint(10, 99)}{self.invoice_seq:06d}",  # unique per claim
            "siret_opticien": opt["siret"], "nom_opticien": opt["nom"], "rpps_prescripteur": rpps,
            "date_prescription": d_presc, "num_adherent": adh["id_adherent"], "nir_beneficiaire": adh["nir"],
            "date_soins": d_soins, "date_facture": d_soins, "type_equipement": "MONTURE_VERRES",
            "classe": classe, "categorie_verres": cat, "montant_monture": monture,
            "montant_verres": money(total - monture), "montant_total": total, "base_remboursement_ro": base,
            "montant_rembourse_ro": ro, "montant_demande_amc": amc,
        }

    def noemie_for(self, c: dict, d_liq: date) -> dict:
        return {
            "id_decompte": f"NOE{c['id_demande'][3:]}", "nir": c["nir_beneficiaire"],
            "date_soins": c["date_soins"].isoformat(), "identifiant_ps": c["siret_opticien"],
            "code_lpp": CODE_LPP[c["categorie_verres"]], "base_remboursement": c["base_remboursement_ro"],
            "taux_remboursement": 60, "montant_rembourse_ro": c["montant_rembourse_ro"],
            "date_liquidation": d_liq.isoformat(), "caisse": f"CPAM {c['nir_beneficiaire'][5:7]}",
        }

    def invoice_row(self, c: dict, messy: bool = True) -> dict:
        m = self.mess
        if not messy:
            return {k: (v.isoformat() if isinstance(v, date) else (f"{v:.2f}" if isinstance(v, float) else v))
                    for k, v in c.items()}
        return {
            "id_demande": c["id_demande"], "canal": c["canal"], "date_reception": c["date_reception"].isoformat(),
            "numero_facture": c["numero_facture"], "siret_opticien": m.ident(c["siret_opticien"], "siret"),
            "nom_opticien": m.name(c["nom_opticien"]), "rpps_prescripteur": c["rpps_prescripteur"],
            "date_prescription": m.optional(m.date(c["date_prescription"]), "date_prescription"),
            "num_adherent": c["num_adherent"], "nir_beneficiaire": m.ident(c["nir_beneficiaire"], "nir"),
            "date_soins": m.date(c["date_soins"]), "date_facture": m.date(c["date_facture"]),
            "type_equipement": c["type_equipement"], "classe": c["classe"],
            "categorie_verres": m.code(c["categorie_verres"]), "montant_monture": m.amount(c["montant_monture"]),
            "montant_verres": m.amount(c["montant_verres"]), "montant_total": m.amount(c["montant_total"]),
            "base_remboursement_ro": m.optional(m.amount(c["base_remboursement_ro"]), "base_remboursement"),
            "montant_rembourse_ro": m.amount(c["montant_rembourse_ro"]),
            "montant_demande_amc": m.amount(c["montant_demande_amc"]),
        }

    # ---------------- writers ----------------
    def write_csv(self, path: Path, columns, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=columns, quoting=csv.QUOTE_MINIMAL)
            w.writeheader()
            w.writerows(rows)

    def write_jsonl(self, path: Path, docs):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for d in docs:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")

    # ---------------- main flow ----------------
    def run(self):
        a, rng = self.a, self.rng
        self.load_refs()
        raw = self.out / "raw"

        # 1) CRM initial snapshot
        adherents = [self.make_adherent(i + 1, self.start) for i in range(a.adherents)]
        by_id = {x["id_adherent"]: x for x in adherents}
        self.write_csv(raw / "dt=history" / "crm" / "adherents.csv", CRM_COLUMNS, [self.crm_row(x) for x in adherents])
        last_equipment: dict[str, date] = {}

        # 2) History: 24 months of legit, already-paid claims (clean files)
        hist_claims, hist_noemie = [], []
        h_start = self.start - timedelta(days=730)
        for adh in rng.sample(adherents, k=min(len(adherents), a.history_claims)):
            d = h_start + timedelta(days=rng.randint(0, 720))
            if d < adh["date_debut_contrat"]:
                continue
            c = self.build_claim(adh, d, d + timedelta(days=rng.randint(0, 3)), rng.choice(self.opticiens),
                                 rng.choice(self.prescripteurs), "TIERS_PAYANT")
            hist_claims.append(c)
            hist_noemie.append(self.noemie_for(c, c["date_reception"]))
            last_equipment[adh["id_adherent"]] = max(d, last_equipment.get(adh["id_adherent"], d))
        hist_claims.sort(key=lambda c: c["date_reception"])
        self.write_csv(raw / "dt=history" / "factures" / "factures_optique_history.csv", INVOICE_COLUMNS,
                       [self.invoice_row(c, messy=False) for c in hist_claims])
        self.write_jsonl(raw / "dt=history" / "noemie" / "noemie_history.jsonl", hist_noemie)
        reimbursed = [(c["siret_opticien"], c["numero_facture"], c["num_adherent"]) for c in hist_claims]

        # 3) Daily batches
        pending_noemie: list[dict] = []   # statements that arrive the next day
        late_day = None if (a.late_noemie_date or "none").lower() == "none" else date.fromisoformat(a.late_noemie_date)
        drift_from = date.fromisoformat(a.schema_drift_from) if a.schema_drift_from else None
        resiliated: list[dict] = []
        next_adh = a.adherents + 1
        counts = {t: 0 for t in FRAUD_TYPES}
        last_idx = len(self.days) - 1
        # day index by which each rule must have reached its minimum (F2 must be evaluable: outside the grace period)
        deadline = {t: (last_idx - F2_GRACE_DAYS if t == "F2_SANS_DECOMPTE_NOEMIE" else last_idx) for t in FRAUD_TYPES}

        for idx, day in enumerate(self.days):
            folder = raw / f"dt={day.isoformat()}"
            ts = datetime.combine(day, time(7, 30))

            # 3a) CRM changes of the day: new members, address changes, resiliations
            changes = []
            for _ in range(max(1, a.adherents // 400)):
                x = self.make_adherent(next_adh, day)
                x["date_debut_contrat"], x["updated_at"] = day, ts + timedelta(minutes=rng.randint(0, 600))
                next_adh += 1
                adherents.append(x)
                by_id[x["id_adherent"]] = x
                changes.append(x)
            for x in rng.sample(adherents, k=max(1, a.adherents // 300)):
                cp, ville = rng.choice(VILLES)
                x["code_postal"], x["ville"] = cp, ville
                x["updated_at"] = ts + timedelta(minutes=rng.randint(0, 600))
                changes.append(x)
            for x in rng.sample([y for y in adherents if y["statut"] == "ACTIF"], k=max(1, a.adherents // 800)):
                x["statut"], x["date_fin_contrat"] = "RESILIE", day          # effective the day it is recorded
                x["updated_at"] = ts + timedelta(minutes=rng.randint(0, 600))
                resiliated.append(x)
                changes.append(x)
            uniq = {c["id_adherent"]: c for c in changes}
            self.write_csv(folder / "crm" / "adherents_changes.csv", CRM_COLUMNS, [self.crm_row(x) for x in uniq.values()])

            # 3b) Legit claims of the day
            claims, noemie_today, noemie_tomorrow = [], [], []
            prev_equipment = {}
            n = max(5, int(rng.gauss(a.claims_per_day, a.claims_per_day * 0.15)))
            active = [x for x in adherents if x["statut"] == "ACTIF"]
            tries = 0
            while len(claims) < n and tries < n * 20:
                tries += 1
                adh = rng.choice(active)
                d_soins = day - timedelta(days=rng.randint(1, 20))
                prev = last_equipment.get(adh["id_adherent"])
                if prev and (d_soins - prev).days < RENOUVELLEMENT_JOURS:
                    continue
                if d_soins < adh["date_debut_contrat"]:
                    continue
                canal = "TIERS_PAYANT" if rng.random() < 0.7 else "APP_ADHERENT"
                c = self.build_claim(adh, d_soins, day, rng.choice(self.opticiens), rng.choice(self.prescripteurs), canal)
                claims.append(c)
                prev_equipment[c["id_demande"]] = prev
                last_equipment[adh["id_adherent"]] = d_soins
                (noemie_tomorrow if rng.random() < 0.2 else noemie_today).append(self.noemie_for(c, day))

            # 3b-bis) Unusable legit claims (NOT fraud): silver must put them in quarantine. Chosen BEFORE the frauds,
            # and removed from the history used by F1 / F5, so that no fraud depends on a quarantined claim.
            quarantined = {}
            for c in rng.sample(claims, k=min(len(claims), max(1, round(len(claims) * a.invalid_rate)))):
                quarantined[c["id_demande"]] = rng.choice(["MONTANT_NEGATIF", "DATE_SOINS_INVALIDE"])
                prev = prev_equipment[c["id_demande"]]
                if prev is None:
                    last_equipment.pop(c["num_adherent"], None)
                else:
                    last_equipment[c["num_adherent"]] = prev
                self.quarantine_key.append({"id_demande": c["id_demande"], "reason": quarantined[c["id_demande"]],
                                            "date_reception": day.isoformat()})

            # 3c) Injected frauds: random mix, then top-ups so that every rule reaches its minimum in time,
            # and at least one F5 on the last day (the case opened during the live demo)
            def add(ftype):
                c = self.inject(ftype, day, active, last_equipment, reimbursed, resiliated, by_id)
                if c is None:
                    return False
                claims.append(c)
                counts[ftype] += 1
                if ftype != "F2_SANS_DECOMPTE_NOEMIE":
                    noemie_today.append(self.noemie_for(c, day))
                return True

            n_fraud = sum(1 for _ in range(len(claims)) if rng.random() < a.fraud_rate)
            for _ in range(n_fraud):
                add(weighted(rng, FRAUD_MIX))
            for ftype in FRAUD_TYPES:
                if idx > deadline[ftype] or counts[ftype] >= a.min_per_rule:
                    continue
                needed = math.ceil((a.min_per_rule - counts[ftype]) / (deadline[ftype] - idx + 1))
                done = attempts = 0
                while done < needed and attempts < 80:
                    attempts += 1
                    done += add(ftype)
            if idx == last_idx and not any(r["fraud_type"] == "F5_FACTURE_REUTILISEE" and r["date_reception"] == day.isoformat()
                                           for r in self.answer_key):
                attempts = 0
                while attempts < 80 and not add("F5_FACTURE_REUTILISEE"):
                    attempts += 1

            # 3d) Technical resends (NOT fraud): the same claim sent twice by the channel
            rows = [self.invoice_row(c) for c in claims]
            for r, c in zip(rows, claims):                   # make the quarantined claims unusable
                reason = quarantined.get(c["id_demande"])
                if reason == "MONTANT_NEGATIF":
                    r["montant_demande_amc"] = f"-{c['montant_demande_amc']:.2f}"
                elif reason == "DATE_SOINS_INVALIDE":
                    r["date_soins"] = rng.choice([f"{day.year}-02-30", f"31/02/{day.year}", f"{day.year}0231"])
            for r in rng.sample(rows, k=max(0, int(len(rows) * a.duplicate_rate))):
                rows.append(dict(r))
                self.noise_rows.append({"id_demande": r["id_demande"], "noise": "TECHNICAL_RESEND", "date": day.isoformat()})
                self.mess.report["technical_resend"] = self.mess.report.get("technical_resend", 0) + 1
            rng.shuffle(rows)
            columns = list(INVOICE_COLUMNS)
            if drift_from and day >= drift_from:            # schema drift: a new column appears upstream
                columns.append("code_reseau_partenaire")
                for r in rows:
                    r["code_reseau_partenaire"] = rng.choice(["", "RES01", "RES02"])
            self.write_csv(folder / "factures" / f"factures_optique_{day:%Y%m%d}.csv", columns, rows)
            for c in claims:
                if c["id_demande"] not in quarantined:
                    reimbursed.append((c["siret_opticien"], c["numero_facture"], c["num_adherent"]))

            # 3e) NOEMIE: today's statements + yesterday's late ones (unless the incident is simulated)
            docs = pending_noemie + noemie_today
            if late_day and day == late_day:
                pending_noemie = docs + noemie_tomorrow      # nothing delivered today: the file is late
                self.mess.report["noemie_file_late_" + day.isoformat()] = len(docs)
            else:
                self.write_jsonl(folder / "noemie" / f"noemie_{day:%Y%m%d}.jsonl", docs)
                pending_noemie = noemie_tomorrow

        if pending_noemie:                                   # statements of the last day arrive the day after
            d_after = self.days[-1] + timedelta(days=1)
            self.write_jsonl(raw / f"dt={d_after.isoformat()}" / "noemie" / f"noemie_{d_after:%Y%m%d}.jsonl", pending_noemie)

        self.write_outputs()
        short = {t: n for t, n in counts.items() if n < a.min_per_rule}
        if short:
            raise SystemExit(f"Could not reach --min-per-rule {a.min_per_rule} for {short}: use more days or adherents.")

    def inject(self, ftype, day, active, last_equipment, reimbursed, resiliated, by_id):
        rng = self.rng
        d_soins = day - timedelta(days=rng.randint(1, 15))
        canal = "APP_ADHERENT" if rng.random() < 0.75 else "TIERS_PAYANT"
        opt, rpps = rng.choice(self.opticiens), rng.choice(self.prescripteurs)
        detail = ""

        if ftype == "F1_RENOUVELLEMENT_PRECOCE":
            cands = [i for i, d in last_equipment.items()
                     if 30 < (d_soins - d).days < RENOUVELLEMENT_JOURS and by_id[i]["statut"] == "ACTIF"]
            if not cands:
                return None
            adh = by_id[rng.choice(cands)]
            detail = f"previous equipment on {last_equipment[adh['id_adherent']].isoformat()}"
            last_equipment[adh["id_adherent"]] = d_soins
        elif ftype == "F7_ADHERENT_RESILIE":
            cands = [x for x in resiliated if x["date_fin_contrat"] < d_soins]
            if not cands:
                return None
            adh = rng.choice(cands)
            if (prev := last_equipment.get(adh["id_adherent"])) and (d_soins - prev).days < RENOUVELLEMENT_JOURS:
                return None                                   # keep one fraud mechanism per claim
            detail = f"contract ended on {adh['date_fin_contrat'].isoformat()}"
        else:
            adh = rng.choice(active)
            if (prev := last_equipment.get(adh["id_adherent"])) and (d_soins - prev).days < RENOUVELLEMENT_JOURS:
                return None                                   # keep one fraud mechanism per claim
            last_equipment[adh["id_adherent"]] = d_soins
        if d_soins < adh["date_debut_contrat"]:
            return None

        if ftype == "F4_OPTICIEN_FANTOME":
            opt = rng.choice(self.ghosts)
            detail = "SIRET not registered in SIRENE"
        if ftype == "F6_PRESCRIPTEUR_INVALIDE":
            rpps = rng.choice(self.fake_prescripteurs)
            detail = "RPPS not in the RPPS directory"
        c = self.build_claim(adh, d_soins, day, opt, rpps, canal)
        if ftype == "F2_SANS_DECOMPTE_NOEMIE":
            detail = "no NOEMIE statement will ever arrive"
        if ftype == "F3_MONTANT_GONFLE":
            c["classe"], c["base_remboursement_ro"], c["montant_rembourse_ro"] = "B", 0.10, 0.06
            factor = rng.uniform(2.2, 3.5)
            c["montant_total"] = money(min(PLAFONDS[c["categorie_verres"]], 400) * factor)
            c["montant_monture"] = money(min(100.0, c["montant_total"] * 0.2))
            c["montant_verres"] = money(c["montant_total"] - c["montant_monture"])
            c["montant_demande_amc"] = money(c["montant_total"] - 0.06)
            detail = f"claimed {c['montant_demande_amc']} > ceiling {PLAFONDS[c['categorie_verres']]}"
        if ftype == "F5_FACTURE_REUTILISEE":
            others = [r for r in reimbursed if r[2] != adh["id_adherent"]]
            if not others:
                return None
            siret, numero, original = rng.choice(others)
            c["siret_opticien"], c["numero_facture"] = siret, numero
            c["nom_opticien"] = next((o["nom"] for o in self.opticiens + self.ghosts if o["siret"] == siret), "OPTICIEN")
            detail = f"invoice {numero} already reimbursed to {original}"

        self.answer_key.append({"id_demande": c["id_demande"], "fraud_type": ftype, "date_reception": day.isoformat(),
                                "num_adherent": c["num_adherent"], "siret_opticien": c["siret_opticien"],
                                "montant_demande_amc": f"{c['montant_demande_amc']:.2f}", "detail": detail})
        return c

    def write_outputs(self):
        ak = self.out / "answer_key"
        self.write_csv(ak / "fraud_answer_key.csv",
                       ["id_demande", "fraud_type", "date_reception", "num_adherent", "siret_opticien",
                        "montant_demande_amc", "detail"], self.answer_key)
        self.write_csv(ak / "quarantine_key.csv", ["id_demande", "reason", "date_reception"], self.quarantine_key)
        (ak / "references_used.json").write_text(json.dumps(
            {"legit_opticiens_siret": [o["siret"] for o in self.opticiens],
             "ghost_opticiens_siret": [o["siret"] for o in self.ghosts],
             "legit_prescripteurs_rpps": self.prescripteurs, "fake_prescripteurs_rpps": self.fake_prescripteurs},
            indent=1), encoding="utf-8")
        counts = {}
        for r in self.answer_key:
            counts[r["fraud_type"]] = counts.get(r["fraud_type"], 0) + 1
        (ak / "noise_report.json").write_text(json.dumps(
            {"cell_level_noise": self.mess.report, "technical_resends": self.noise_rows,
             "note": "Technical resends are NOT fraud: same id_demande, identical content. Deduplicate them in silver."},
            indent=2, ensure_ascii=False), encoding="utf-8")
        (ak / "generation_manifest.json").write_text(json.dumps(
            {"generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "parameters": vars(self.a),
             "first_day": self.days[0].isoformat(), "last_day": self.days[-1].isoformat(),
             "f2_grace_days": F2_GRACE_DAYS, "quarantined_claims": len(self.quarantine_key),
             "synthetic_references": self.synthetic_refs, "fraud_counts": counts,
             "fraud_definitions": FRAUD_TYPES, "plafonds_contrat_responsable": PLAFONDS,
             "garanties_formules": GARANTIES}, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"Done. Frauds injected: {sum(counts.values())} {counts}")
        print(f"Quarantine (invalid legit claims): {len(self.quarantine_key)}")
        print(f"Synthetic references used: {self.synthetic_refs}")
        print(f"Output: {self.out.resolve()}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="data", help="output folder (default: data)")
    p.add_argument("--refs-dir", default=str(REF_DIR_DEFAULT),
                   help="folder with the frozen opticiens_sirene.csv / ophtalmos_rpps.csv (default: data_generator/ref)")
    p.add_argument("--allow-synthetic", action="store_true", help="CI only: synthetic SIRET/RPPS if the references are missing")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--start-date", default="2026-10-26", help="first daily batch (YYYY-MM-DD)")
    p.add_argument("--days", type=int, default=10, help="number of daily batches")
    p.add_argument("--adherents", type=int, default=8000)
    p.add_argument("--opticiens", type=int, default=80, help="legit opticians used")
    p.add_argument("--prescripteurs", type=int, default=150)
    p.add_argument("--history-claims", type=int, default=2500, help="claims in the 24-month history")
    p.add_argument("--claims-per-day", type=int, default=160)
    p.add_argument("--fraud-rate", type=float, default=0.07)
    p.add_argument("--duplicate-rate", type=float, default=0.01, help="technical resends (not fraud)")
    p.add_argument("--invalid-rate", type=float, default=0.005, help="legit claims made unusable (quarantine), min 1/day")
    p.add_argument("--min-per-rule", type=int, default=5, help="minimum frauds per rule F1..F7")
    p.add_argument("--mess", choices=["low", "medium", "high"], default="medium")
    p.add_argument("--late-noemie-date", default="2026-10-30",
                   help="incident 2: no NOEMIE file that day, delivered the day after (YYYY-MM-DD, or 'none')")
    p.add_argument("--schema-drift-from", default=None, help="incident: new column in invoices from that day")
    args = p.parse_args()
    Generator(args).run()


if __name__ == "__main__":
    main()

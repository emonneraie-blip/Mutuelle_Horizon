# Contracts between pipeline stages

Owner of this file for the BRONZE part: **Lucas (ingestion)**. Any change = pull request reviewed by Clément (transformation).

## 1. Snowflake objects

| Object | Name | Owner |
|---|---|---|
| Database | `MUTUELLE_FRAUD` | platform (Terraform) |
| Schemas | `BRONZE` (owned by `INGEST_ROLE`), `SILVER`, `GOLD`, `OPS` (owned by `TRANSFORM_ROLE`) | Lucas / Clément |
| Warehouses | `INGEST_WH`, `TRANSFORM_WH`, `BI_WH` (XSMALL, auto-suspend 60 s) | platform |
| Roles | `INGEST_ROLE` (writes BRONZE), `TRANSFORM_ROLE` (reads BRONZE, writes SILVER/GOLD/OPS), `ANALYST_ROLE` (reads GOLD.KPI_FRAUDE_QUOTIDIEN only) | platform |
| Service users | `SVC_INGEST` → `INGEST_ROLE`, `SVC_TRANSFORM` → `TRANSFORM_ROLE`, `SVC_TERRAFORM` → SYSADMIN + SECURITYADMIN (RSA key only) | platform |
| Landing zone | internal stage `BRONZE.LANDING`, paths `factures/<date>/`, `noemie/<date>/`, `crm/<run_id>/`, `rpps/<run_id>/` | ingestion |

## 2. Sources → BRONZE tables

Every bronze table keeps the data **as received** + lineage columns (`_SOURCE_FILE`, `_FILE_ROW`, `_BATCH_DATE`, `_LOADED_AT`, `_RUN_ID`). Nothing is cleaned in bronze.

| Source | Real / synthetic | Ingestion method | Bronze table | Grain | Idempotence |
|---|---|---|---|---|---|
| Optical claims (tiers payant + adherent app), daily CSV | synthetic, frauds injected | **Batch files**: PUT + `COPY INTO` | `FACTURES_OPTIQUE` (all VARCHAR) | one line per received claim (technical resends included!) | COPY load history: a file is never loaded twice |
| NOEMIE statements (Sécurité sociale), daily JSON lines | synthetic | **Batch semi-structured**: PUT + `COPY INTO` VARIANT | `NOEMIE_DECOMPTES` (`RAW` VARIANT) | one statement | COPY load history |
| CRM adherents & contracts, Postgres `crm.adherents` | synthetic | **Incremental pull**: watermark `UPDATED_AT` + `MERGE` | `ADHERENTS` (typed, **minimised**) | latest version per `ID_ADHERENT` | MERGE on key, `>=` watermark |
| Opticians, API Recherche d'entreprises (SIRENE) | **real** | **API pull**, only SIRETs not yet checked | `SIRENE_ETABLISSEMENTS` (`RAW` VARIANT + `FOUND`, `ETAT_ADMINISTRATIF`) | one SIRET | only new SIRETs are called |
| Ophthalmologists, Annuaire Santé (RPPS) open data | **real** | **Batch reference, full refresh** (stream + filter) | `RPPS_PRESCRIPTEURS` | one RPPS number | DELETE + COPY in one transaction |
| Every run | — | — | `LOAD_AUDIT` | one job run | — |

### 2.1 `FACTURES_OPTIQUE` (CSV header = contract, any change = schema drift = job stops)

`id_demande, canal, date_reception, numero_facture, siret_opticien, nom_opticien, rpps_prescripteur, date_prescription, num_adherent, nir_beneficiaire, date_soins, date_facture, type_equipement, classe, categorie_verres, montant_monture, montant_verres, montant_total, base_remboursement_ro, montant_rembourse_ro, montant_demande_amc`

- `id_demande`: id given by the mutuelle when the claim is received. **Same id twice = technical resend (not fraud) → deduplicate in silver.**
- `canal`: `TIERS_PAYANT` (sent by the optician) or `APP_ADHERENT` (uploaded by the adherent).
- `classe`: `A` = 100 % Santé, `B` = free pricing. `montant_demande_amc` = what the mutuelle is asked to pay.

### 2.2 `ADHERENTS` columns (data minimisation)

`ID_ADHERENT, FORMULE, DATE_DEBUT_CONTRAT, DATE_FIN_CONTRAT, STATUT, UPDATED_AT` + lineage (F3 uses `FORMULE`, F7 uses `DATE_FIN_CONTRAT`).
NIR, name, first name, birth date, e-mail, phone, postcode and city exist in the CRM but are **never copied to Snowflake**: no rule needs them.
The only NIR in Snowflake is `nir_beneficiaire` on the claim (needed to match NOEMIE for F2): BRONZE is readable by `INGEST_ROLE` and `TRANSFORM_ROLE` only, and silver keeps `SHA2(NIR)` only.

### 2.3 `NOEMIE_DECOMPTES.RAW` keys

`id_decompte, nir, date_soins, identifiant_ps (SIRET of the optician), code_lpp, base_remboursement, taux_remboursement, montant_rembourse_ro, date_liquidation, caisse`.
Matching key claim ↔ statement: **(nir, siret, date_soins)**. About 20 % of the statements arrive **the day after** the claim, and the whole file can be one day late (incident of 2026-10-30): a statement can therefore arrive **up to 2 days** after the claim.

## 3. Mess injected on purpose (silver must handle it)

See `data/answer_key/noise_report.json` for the exact counts.

| Mess | Example | Silver fix |
|---|---|---|
| Dates in 3 formats | `2026-10-21`, `21/10/2026`, `20261021` | `COALESCE(TRY_TO_DATE(v,'YYYY-MM-DD'), TRY_TO_DATE(v,'DD/MM/YYYY'), TRY_TO_DATE(v,'YYYYMMDD'))` |
| Amounts as text | `90,20`, `1 234,50 €` | remove `€` and spaces, decimal comma → point, `TRY_TO_NUMBER(v, 12, 2)` |
| Missing markers | `''`, `N/A`, `null`, `-` | → NULL |
| Codes with case / spaces | ` simple `, `Simple` | `UPPER(TRIM())` |
| Ids with spaces | `074 789 535 205 83` (SIRET), NIR in blocks | `REGEXP_REPLACE(v, '[^0-9]', '')` |
| Names in capitals | `OPTIC BASTILLE` | `INITCAP` if displayed |
| Technical resends | same `id_demande` twice | `QUALIFY ROW_NUMBER() OVER (PARTITION BY id_demande ORDER BY _LOADED_AT, _FILE_ROW) = 1` |
| **Unusable claims** (1 per day, always legitimate) | `montant_demande_amc` = `-120.00`, `date_soins` = `2026-02-30` / `31/02/2026` / `20260231` | → `slv_factures_quarantaine` with the reason (`MONTANT_NEGATIF`, `DATE_SOINS_INVALIDE`, `DATE_RECEPTION_INVALIDE`, `MONTANT_MANQUANT`), excluded from every rule **and from the history** used by F1 / F5. Expected list: `quarantine_key.csv` |

## 4. Fraud rules (one injected mechanism per fraudulent claim)

Exact definitions = `data_generator/validate.py` (executable specification). Expected result on the generated data, **every morning** (`validate.py --each-day`): **100 % recall on every evaluable rule, 0 false positive**. The data set guarantees at least 5 evaluable frauds per rule and one F5 on the last day.

| Code | Rule | Data needed |
|---|---|---|
| F1_RENOUVELLEMENT_PRECOCE | full equipment less than 730 days after the previous one, same adherent | claims history |
| F2_SANS_DECOMPTE_NOEMIE | no NOEMIE statement **received up to `batch_date`** with the same (nir, siret, date_soins). **Evaluated only if `date_reception <= batch_date - 2 days`**, otherwise `f2_statut = 'EN_ATTENTE'` (batch D+2 runs on the morning of D+3: a claim waiting for F2 is paid at the earliest on D+3) | NOEMIE |
| F3_MONTANT_GONFLE | classe B and `montant_demande_amc` > min(ceiling of the lens category, guarantee of the formula) | claims + CRM formula |
| F4_OPTICIEN_FANTOME | SIRET not found in SIRENE (or closed) | SIRENE |
| F5_FACTURE_REUTILISEE | (siret, numero_facture) already reimbursed to **another** adherent | claims history |
| F6_PRESCRIPTEUR_INVALIDE | prescriber RPPS not in the RPPS ophthalmologists list | RPPS |
| F7_ADHERENT_RESILIE | `date_soins` after `date_fin_contrat` | CRM |

Contract ceilings (contrat responsable, classe B, simplified): SIMPLE 420 €, MIXTE 560 €, COMPLEXE 700 €, TRES_COMPLEXE 800 €.
Formula guarantees on optics: ESSENTIEL 150 €, CONFORT 300 €, PREMIUM up to the ceiling.

## 5. Answer keys (acceptance tests only)

`data/answer_key/fraud_answer_key.csv`: `id_demande, fraud_type, date_reception, num_adherent, siret_opticien, montant_demande_amc, detail`.
`data/answer_key/quarantine_key.csv`: `id_demande, reason, date_reception`.
They are loaded **only as dbt seeds for the acceptance tests** (`assert_recall_80pct`, quarantine test) and are **never used by the rules**.
`data/answer_key/references_used.json` lists the opticians / prescribers used, for offline validation only.
Reference extracts: `data_generator/ref/opticiens_sirene.csv` (SIRET, postcode, town, status) and `ophtalmos_rpps.csv` (RPPS, profession, specialty, postcode, town): real public data, **frozen and versioned, no names**.

## 6. Ethics

All adherents, NIR numbers and claims are **fictitious**. Real SIRET (SIRENE) and RPPS numbers are only used on legitimate claims or as the letterhead *forged* by a fictitious adherent, and **the optician name on every claim is fictitious**: no real optician or doctor is displayed next to a fraud. Do not publish rankings of real opticians. RPPS data is reduced to the number, profession and specialty (no names).

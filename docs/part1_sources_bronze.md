# Partie 1 · Sources → BRONZE (owner : Lucas)

Ce dossier contient tout le tronçon **sources → bronze** du pipeline « Mutuelle Horizon Santé — détection de fraude optique » :

```
data_generator/   generate.py (données réalistes + fraudes + corrigé)   validate.py (règles de référence, test d'acceptation)
ingestion/        jobs Python (1 job = 1 source), sql/bronze_ddl.sql, Dockerfile, requirements.txt figé
docs/             contracts.md (contrat bronze ↔ silver, règles de fraude), ce runbook
docker-compose.crm.yml   Postgres du CRM (source opérationnelle)
.env.example      variables à copier dans .env (jamais commité)
```

## Ce qui a déjà été testé (et ce qui ne l'a pas été)

| Testé | Résultat |
|---|---|
| Générateur, 5 seeds, mess `high`, incident NOEMIE en retard | `validate.py` : 100 % de rappel sur les 7 règles, 0 faux positif |
| Reproductibilité | même seed → fichiers identiques au bit près |
| `seed_postgres` + requête incrémentale sur un vrai Postgres 16 | OK, rejeu idempotent |
| Détection du schema drift (nouvelle colonne) | le job s'arrête avant de charger, statut `SCHEMA_DRIFT` |
| Extraction RPPS sur un fichier au format officiel | OK (filtre ophtalmologie, dédoublonnage, sans les noms) |
| Dépendances figées (`requirements.txt`) | résolues et importées en Python 3.12 |
| SQL Snowflake (PUT / COPY / MERGE) | généré et relu, **pas exécuté** : à valider à l'étape 6 ci-dessous |
| API SIRENE, téléchargement RPPS, `docker build` | **pas testés ici** (réseau bloqué) : à lancer depuis le Mac |

## Pas à pas

Toutes les commandes se lancent à la racine du repo.

### 0. Prérequis (une fois)

Owner : **Lucas**. Prérequis : `terraform/bootstrap_admin.sql` exécuté, puis le Terraform d'Eliott appliqué (base, `INGEST_WH`, `INGEST_ROLE`, `TRANSFORM_ROLE`, compte `SVC_INGEST`).

```bash
# clé du compte de service SVC_INGEST, sur la machine de démo — la clé privée ne quitte jamais ~/keys/mutuelle
mkdir -p ~/keys/mutuelle && openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out ~/keys/mutuelle/svc_ingest.p8 -nocrypt
openssl rsa -in ~/keys/mutuelle/svc_ingest.p8 -pubout -out ~/keys/mutuelle/svc_ingest.pub
cat ~/keys/mutuelle/svc_ingest.pub   # clé PUBLIQUE à donner à Eliott (variable Terraform)
cp .env.example .env                 # SNOWFLAKE_USER=SVC_INGEST, SNOWFLAKE_PRIVATE_KEY_FILE=/secrets/svc_ingest.p8
docker build -t fraud-ingest:1.0.0 ingestion/
```

Raccourci pour lancer un job dans le conteneur (même montage que dans le DAG Airflow) :

```bash
run() { docker run --rm --env-file .env -v "$PWD/data:/data" -v "$HOME/keys/mutuelle:/secrets:ro" fraud-ingest:1.0.0 python -m "$@"; }
```

### 1. Références réelles (internet, pas besoin de Snowflake)

```bash
run jobs.fetch_sirene catalogue --departements 75 92 93 94 --max 400   # vrais opticiens actifs -> data/ref/opticiens_sirene.csv
run jobs.load_rpps --extract-only                                     # ~800 Mo lus en streaming -> data/ref/ophtalmos_rpps.csv
```

### 2. Générer les données (seed fixe = démo reproductible)

```bash
python3 data_generator/generate.py --seed 42            # 10 jours à partir du 2026-10-26 + 24 mois d'historique
python3 data_generator/validate.py --data data          # attendu : VALIDATION OK
```

La dernière ligne de `generate.py` doit indiquer `Synthetic references used: {'opticiens': False, 'prescripteurs': False}` (= les vraies références de l'étape 1 sont utilisées).

### 3. CRM Postgres (la source opérationnelle)

```bash
docker compose -f docker-compose.crm.yml up -d
run jobs.seed_postgres --date history                   # 8 000 adhérents, joue le rôle de l'application CRM
```

### 4. Créer la couche bronze

```bash
run jobs.bootstrap_bronze
```

### 5. Charger l'historique et les références

```bash
run jobs.load_invoices --date history
run jobs.load_noemie --date history
run jobs.load_adherents_incremental       # 1er run = chargement complet (watermark 1900-01-01)
run jobs.load_rpps --reuse-extract
```

### 6. Charger les jours, comme le fera Airflow

```bash
for d in 2026-10-26 2026-10-27 2026-10-28; do run jobs.run_day --date $d --simulate-crm; done
```

`run_day` enchaîne : activité CRM du jour → incrémental adhérents → factures → NOEMIE → vérification SIRENE des nouveaux SIRET.

Vérifications dans Snowsight :

```sql
SELECT JOB, BATCH_DATE, STATUS, FILES_LOADED, ROWS_LOADED, ENDED_AT FROM MUTUELLE_FRAUD.BRONZE.LOAD_AUDIT ORDER BY ENDED_AT DESC;
SELECT _BATCH_DATE, COUNT(*), COUNT(DISTINCT ID_DEMANDE) FROM MUTUELLE_FRAUD.BRONZE.FACTURES_OPTIQUE GROUP BY 1 ORDER BY 1;
SELECT FOUND, COUNT(*) FROM MUTUELLE_FRAUD.BRONZE.SIRENE_ETABLISSEMENTS GROUP BY 1;
```

**Preuve d'idempotence** (à montrer à l'oral) : relancer `run jobs.run_day --date 2026-10-27` donne `ALREADY_LOADED`, `0 rows`, et `MERGE: 0 inserted, 0 updated`.

### 7. Les deux incidents (pour C6)

1. **Flux NOEMIE en retard** : `python3 data_generator/generate.py --seed 42 --late-noemie-date 2026-10-30` ; le job NOEMIE de ce jour enregistre `NO_FILE`, et c'est le test de fraîcheur dbt qui alerte.
2. **Schema drift** : `--schema-drift-from 2026-10-31` ajoute une colonne aux factures ; `load_invoices` s'arrête avec `SCHEMA_DRIFT` **avant** de charger, Airflow alerte. Correction : mise à jour du contrat + DDL + PR relue.

## Commandes à donner au DAG Airflow (owner plateforme)

| Tâche | Commande dans l'image `fraud-ingest:1.0.0` |
|---|---|
| `crm_activity` (simulation, démo uniquement) | `python -m jobs.seed_postgres --date {{ ds }}` |
| `ingest_adherents` | `python -m jobs.load_adherents_incremental` |
| `ingest_factures` | `python -m jobs.load_invoices --date {{ ds }}` |
| `ingest_noemie` | `python -m jobs.load_noemie --date {{ ds }}` |
| `check_sirene` (après `ingest_factures`) | `python -m jobs.fetch_sirene lookup` |
| `refresh_rpps` (hebdomadaire) | `python -m jobs.load_rpps` |

Montages : `./data → /data`, `~/keys/mutuelle → /secrets` (lecture seule). Compte : `SVC_INGEST`. Variables : celles de `.env.example`. Dans le DAG, `{{ ds }}` devient `{{ macros.ds_add(ds, -1) }}` (on traite le lot de la veille).

## Ce que l'owner de la transformation reçoit

Les tables `BRONZE.*` décrites dans `docs/contracts.md`, le corrigé `data/answer_key/fraud_answer_key.csv`, et `data_generator/validate.py`, qui est la spécification exécutable du nettoyage et des 7 règles.

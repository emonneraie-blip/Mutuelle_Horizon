# Mutuelle Horizon Santé · optical claims fraud detection

Fictitious French health mutual (300,000 members). Every morning at 06:00, a daily batch pipeline lists the optical claims
the anti-fraud manager must check **before paying them**, using 7 fraud rules (F1–F7).

Data Engineering & Cloud Infrastructure — Albert School · Group 1: Lucas Stefani, Clément Badalucco, Eliott Monneraie.

```
5 sources (claims CSV, NOEMIE JSON, CRM Postgres, SIRENE API, RPPS open data)
  → ingestion (Python in Docker)  → BRONZE  → dbt → SILVER → GOLD → Streamlit dashboard
  orchestrated by Airflow · infrastructure by Terraform · CI by GitHub Actions · Snowflake
```

| Folder | What | Owner |
|---|---|---|
| `data_generator/` | realistic synthetic data + injected frauds + answer key + `validate.py` | Lucas |
| `ingestion/` | one job per source, BRONZE DDL, image `fraud-ingest:1.0.0` | Lucas |
| `transformation/` | dbt project, image `fraud-dbt:1.0.0` | Clément |
| `dashboard/` | Streamlit in Snowflake | Clément |
| `airflow/` | daily DAG `mutuelle_fraud_daily` | Eliott |
| `terraform/` | Snowflake infrastructure as code, `bootstrap_admin.sql` | Eliott |
| `docs/` | contracts, runbook, security, FinOps, incidents | all |

## Run it from scratch

```bash
cp .env.example .env                                         # fill in; keys stay in ~/keys/mutuelle, never in Git
python3 data_generator/generate.py --seed 42                 # official data set (real references frozen in data_generator/ref/)
python3 data_generator/validate.py --data data --each-day    # expected: VALIDATION OK
docker build -t fraud-ingest:1.0.0 ingestion/ && docker compose -f docker-compose.crm.yml up -d --wait
# Snowflake objects: terraform/ (see terraform/README.md), then the ingestion runbook: docs/part1_sources_bronze.md
```

## Transformation and dashboard

```bash
cd transformation
export SNOWFLAKE_ACCOUNT=<see .env> SNOWFLAKE_USER=<your user> SNOWFLAKE_PRIVATE_KEY_FILE=<path to your .p8 key>
export DBT_PROFILES_DIR=. NIR_SALT=<shared secret, never in Git>   # 16 characters minimum, otherwise dbt refuses to start
dbt build --vars '{batch_date: 2026-11-03}'                        # builds SILVER and GOLD and runs every test; expected: no error
docker build -t fraud-dbt:1.0.0 .                                  # image used by Airflow
```

Dashboard: in Snowsight, Projects > Streamlit > `DASHBOARD_ANTI_FRAUDE`, then Start (about 1 minute to start). Details: `transformation/README.md`, `dashboard/README.md`.

Rules of the repo: no direct push on `main`, one branch + one reviewed pull request per change, no secret ever committed.
All people, NIR numbers and claims are fictitious; real SIRET / RPPS numbers are never labelled as fraudsters (see `docs/contracts.md`).

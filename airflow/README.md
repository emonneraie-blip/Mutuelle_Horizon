# airflow/ · owner Eliott

Copy of the RED-401 lab setup (docker-compose, Dockerfile) + `dags/mutuelle_fraud_daily.py`:
`0 6 * * *` Europe/Paris, `max_active_runs=1`, `retries=2`, Discord alert on final failure.
Tasks (DockerOperator, batch = `{{ macros.ds_add(ds, -1) }}`):
`crm_activity` → [`ingest_adherents`, `ingest_factures`, `ingest_noemie`] → `check_sirene` → `dbt_build`.
Exact ingestion commands: `docs/part1_sources_bronze.md` (last section).
Mounts: `./data → /data`, `~/keys/mutuelle → /secrets:ro`. Users: `SVC_INGEST` (ingestion), `SVC_TRANSFORM` (dbt).
Preload = backfill of the logical dates 2026-10-27 → 2026-11-04 (batches 26/10 → 03/11; the live run of 5/11 processes 04/11).
The Airflow backfill CLI needs `-e HOME=/home/airflow` (lab lesson).

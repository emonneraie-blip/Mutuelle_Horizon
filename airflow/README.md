# airflow/ · owner Eliott

Copy of the RED-401 lab setup (docker-compose, Dockerfile) + `dags/mutuelle_fraud_daily.py`:
`0 6 * * *` Europe/Paris, `max_active_runs=1`, `retries=2`, Discord alert on final failure.
Tasks (DockerOperator, batch = `{{ macros.ds_add(ds, -1) }}`):
`crm_activity` → [`ingest_adherents`, `ingest_factures`, `ingest_noemie`] → `check_sirene` → `dbt_build`.
Exact ingestion commands: `docs/part1_sources_bronze.md` (last section).
Mounts: `./data → /data`, `~/keys/mutuelle → /secrets:ro`. Users: `SVC_INGEST` (ingestion), `SVC_TRANSFORM` (dbt).
Preload = backfill of the logical dates 2026-10-27 → 2026-11-04 (batches 26/10 → 03/11; the live run of 5/11 processes 04/11).
The Airflow backfill CLI needs `-e HOME=/home/airflow` (lab lesson).

---

# airflow/ · owner Eliott

DAG `mutuelle_fraud_daily` : chaque jour à 06:00 (Europe/Paris), il traite le lot de la veille.

```
crm_activity -> ingest_adherents ------------------\
             -> ingest_factures -> check_sirene ---- > dbt_build
             -> ingest_noemie ---------------------/
```

- Chaque tâche est un conteneur (`fraud-ingest:1.0.0` de Lucas, `fraud-dbt:1.0.0` de Clément).
- 2 relances par tâche, puis une alerte Discord.
- Un seul run à la fois (`max_active_runs=1`).
- Comptes : `SVC_INGEST` pour l'ingestion, `SVC_TRANSFORM` pour dbt. Les clés sont montées en lecture seule.

## Lancer

```bash
cd airflow
cp .env.example .env          # remplir les chemins ABSOLUS de data/ et des clés
docker compose up -d --build
```

Interface : http://localhost:8080. Activer le DAG avec l'interrupteur, à gauche de son nom.

## Tester sans les images (PIPELINE_DRY_RUN=1)

Chaque tâche affiche sa commande au lieu de la lancer. On vérifie ainsi l'ordre des tâches, la date du lot et les relances.

**Sur la machine de démo, mettre `PIPELINE_DRY_RUN=0`** dans `airflow/.env` (les vraies images `fraud-ingest:1.0.0` et `fraud-dbt:1.0.0` doivent être construites), puis `docker compose up -d` pour relire le `.env`.

## Les dates de la démo

Le DAG traite la veille de sa date logique.
- Préchargement (mercredi) : rattrapage des dates logiques du 27/10 au 04/11, soit les lots du 26/10 au 03/11.
- Run live (jeudi 05/11) : Trigger sans changer la date, ce qui traite le lot du 04/11.

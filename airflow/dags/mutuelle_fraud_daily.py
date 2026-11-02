"""Mutuelle Horizon Santé · pipeline quotidien de détection de fraude optique.

Chaque matin à 06:00 (Europe/Paris), on traite le lot de la VEILLE :

  crm_activity -> ingest_adherents  ----------------------------\
               -> ingest_factures  -> check_sirene  ------------ > dbt_build
               -> ingest_noemie  -------------------------------/

Chaque tâche est un conteneur Docker (fraud-ingest ou fraud-dbt). Airflow décide seulement QUAND et DANS QUEL
ORDRE elles tournent, les relance en cas d'échec, et prévient sur Discord après le dernier échec.

Démo : le run du jeudi 05/11 traite le lot du 04/11 (le DAG traite toujours la veille).
Préchargement : rattrapage des dates logiques du 27/10 au 04/11 (lots du 26/10 au 03/11).
"""
import json
import os
import urllib.request
from datetime import date, timedelta

import pendulum
from airflow.providers.docker.operators.docker import DockerOperator
from airflow.sdk import DAG
from docker.types import Mount

# Le lot traité = la veille de la date logique du run (jamais "aujourd'hui" : les rejeux et rattrapages marchent)
BATCH = "{{ macros.ds_add(ds, -1) }}"

DRY_RUN = os.environ.get("PIPELINE_DRY_RUN", "0") == "1"
INGEST_IMAGE = "fraud-ingest:1.0.0"
DBT_IMAGE = "fraud-dbt:1.0.0"

# Dossiers de la machine montés dans chaque tâche. Les clés sont en LECTURE SEULE et jamais dans une image.
MOUNTS = [
    Mount(source=os.environ.get("HOST_DATA_DIR", "/tmp"), target="/data", type="bind"),
    Mount(source=os.environ.get("HOST_KEYS_DIR", "/tmp"), target="/secrets", type="bind", read_only=True),
]

# Un compte de service par couche : SVC_INGEST écrit BRONZE, SVC_TRANSFORM écrit SILVER / GOLD
ENV_INGEST = {
    "SNOWFLAKE_ACCOUNT": os.environ.get("SNOWFLAKE_ACCOUNT", ""),
    "SNOWFLAKE_DATABASE": os.environ.get("SNOWFLAKE_DATABASE", "MUTUELLE_FRAUD"),
    "SNOWFLAKE_USER": "SVC_INGEST",
    "SNOWFLAKE_ROLE": "INGEST_ROLE",
    "SNOWFLAKE_WAREHOUSE": "INGEST_WH",
    "SNOWFLAKE_PRIVATE_KEY_FILE": "/secrets/svc_ingest.p8",
    "PGHOST": os.environ.get("PGHOST", "host.docker.internal"),
    "PGPORT": os.environ.get("PGPORT", "5433"),
    "PGDATABASE": os.environ.get("PGDATABASE", "mutuelle_crm"),
    "PGUSER": os.environ.get("PGUSER", "crm"),
    "PGPASSWORD": os.environ.get("PGPASSWORD", ""),
    "DATA_DIR": "/data",
    "RUN_ID": "{{ run_id }}",
}

ENV_DBT = {
    "SNOWFLAKE_ACCOUNT": os.environ.get("SNOWFLAKE_ACCOUNT", ""),
    "SNOWFLAKE_DATABASE": os.environ.get("SNOWFLAKE_DATABASE", "MUTUELLE_FRAUD"),
    "SNOWFLAKE_USER": "SVC_TRANSFORM",
    "SNOWFLAKE_ROLE": "TRANSFORM_ROLE",
    "SNOWFLAKE_WAREHOUSE": "TRANSFORM_WH",
    "SNOWFLAKE_PRIVATE_KEY_FILE": "/secrets/svc_transform.p8",
    "NIR_SALT": os.environ.get("NIR_SALT", ""),         # sel secret du hachage du NIR (silver), jamais dans Git
}


def alert_discord(context):
    """Appelée après le DERNIER échec d'une tâche (les relances sont déjà épuisées)."""
    ti = context["task_instance"]
    # context["ds"] = date du RUN. Le lot traité est la veille : c'est lui qu'on annonce.
    lot = (date.fromisoformat(context["ds"]) - timedelta(days=1)).isoformat()
    text = (f":red_circle: Mutuelle Horizon - tâche **{ti.task_id}** en échec pour le lot du "
            f"{lot} (run du {context['ds']}, essai {ti.try_number}). Logs : {ti.log_url}")
    url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if url == "":
        print("ALERTE (pas de webhook Discord configuré) :", text)
        return
    # Discord attend le champ "content"
    req = urllib.request.Request(url, data=json.dumps({"content": text}).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "airflow"})
    urllib.request.urlopen(req, timeout=10)


def task(task_id, image, command, env):
    """Une tâche = un conteneur. En mode DRY_RUN, le conteneur affiche seulement la commande."""
    if DRY_RUN:
        image = "python:3.12.7-slim"
        command = ["echo", "DRY RUN -", task_id, "-", command]
    return DockerOperator(
        task_id=task_id,
        image=image,
        command=command,
        environment=env,
        mounts=MOUNTS,
        mount_tmp_dir=False,
        auto_remove="success",
        docker_url="unix://var/run/docker.sock",
    )


with DAG(
    dag_id="mutuelle_fraud_daily",
    schedule="0 6 * * *",                                  # 06:00 heure de Paris, été comme hiver
    start_date=pendulum.datetime(2026, 10, 27, tz="Europe/Paris"),
    catchup=False,
    max_active_runs=1,                                     # un seul lot à la fois
    default_args={
        "retries": 2,
        "retry_delay": pendulum.duration(minutes=1),
        "on_failure_callback": alert_discord,
    },
    tags=["mutuelle", "fraude"],
) as dag:

    # Commandes données par Lucas (docs/part1_sources_bronze.md)
    crm_activity = task("crm_activity", INGEST_IMAGE, "python -m jobs.seed_postgres --date " + BATCH, ENV_INGEST)
    ingest_adherents = task("ingest_adherents", INGEST_IMAGE, "python -m jobs.load_adherents_incremental", ENV_INGEST)
    ingest_factures = task("ingest_factures", INGEST_IMAGE, "python -m jobs.load_invoices --date " + BATCH, ENV_INGEST)
    ingest_noemie = task("ingest_noemie", INGEST_IMAGE, "python -m jobs.load_noemie --date " + BATCH, ENV_INGEST)
    check_sirene = task("check_sirene", INGEST_IMAGE, "python -m jobs.fetch_sirene lookup", ENV_INGEST)
    dbt_build = task("dbt_build", DBT_IMAGE, "dbt build --vars '{batch_date: " + BATCH + "}'", ENV_DBT)

    crm_activity >> [ingest_adherents, ingest_factures, ingest_noemie]
    ingest_factures >> check_sirene
    [ingest_adherents, ingest_noemie, check_sirene] >> dbt_build

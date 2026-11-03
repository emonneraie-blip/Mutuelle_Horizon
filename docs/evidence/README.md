# Preuves des tests réels (Airflow sur la machine de démo, 03/11/2026)

Captures prises pendant les runs réels du DAG `mutuelle_fraud_daily` (Airflow 3, DockerOperator, Snowflake `MUTUELLE_FRAUD`).
Chaque run du jour J traite le lot de la veille (`batch = ds - 1`).

| # | Capture | Ce qu'elle prouve |
|---|---|---|
| 1 | `01_run_airflow_2026-11-03_vert.png` | Run planifié du 03/11 06:00 (lot du 02/11) : les 6 tâches au vert, durée totale 1 min 02 |
| 2 | `02_incident1_rejeu_already_loaded.png` | **Incident 1, rejeu sans doublon** : `ingest_factures` relancé sur un lot déjà chargé → `batch 2026-11-02: 0 file(s), 0 rows loaded (ALREADY_LOADED); rows in file(s): 185`. `COPY INTO` ne recharge pas un fichier déjà chargé |
| 3 | `03_incident2_dbt_build_echec.png` | **Incident 2, NOEMIE en retard** : run de date logique 31/10 (lot du 30/10, aucun fichier NOEMIE → `NO_FILE`). `dbt_build` échoue 3 fois sur `assert_lot_noemie_present` ; `PASS=31 ERROR=1 SKIP=15` : les modèles GOLD sont sautés, la liste à contrôler n'est pas publiée |
| 4 | `04_incident2_alerte_discord.png` | Alerte Discord envoyée après le 3ᵉ échec, avec le lot concerné et le lien vers les logs |

Après le test de l'incident 2, GOLD a été reconstruit au lot du 03/11 (`dbt build --vars '{batch_date: 2026-11-03}'` → `PASS=46 ERROR=0`).
Procédures et contexte : [`docs/part1_sources_bronze.md`](../part1_sources_bronze.md) (section 7) et `docs/incidents.md`.

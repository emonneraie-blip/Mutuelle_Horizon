# FinOps · coûts du prototype (owner : Eliott)

Principe : on paie seulement le calcul réellement utilisé, on le voit par usage, et un garde-fou coupe les 3 entrepôts avant une mauvaise surprise.

> Chiffres mesurés le 03/11 sur `SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY` (heure de Paris). Ces vues ont jusqu'à 3 h de retard.

## 1. Ce qui coûte, et ce qui est gratuit

| Composant | Coût | Pourquoi |
|---|---|---|
| Snowflake : 3 entrepôts XSMALL | crédits, seulement quand un entrepôt tourne | arrêt automatique après 60 s, démarrage à la demande, suspendus à la création |
| Snowflake : stockage | négligeable (quelques Mo) | quelques milliers de lignes par jour |
| Snowflake : compute pool du dashboard (`SYSTEM_COMPUTE_POOL_CPU`) | crédits, tant que l'application Streamlit tourne | **non couvert par le resource monitor**, qui ne surveille que les entrepôts |
| Airflow + Docker | 0 € | tournent sur la machine de démo |
| HCP Terraform (state), GitHub (repo + CI), Discord (alertes) | 0 € | offres gratuites |

Un entrepôt par usage (`INGEST_WH`, `TRANSFORM_WH`, `BI_WH`) permet de lire le coût de l'ingestion, de dbt et du dashboard séparément.

## 2. Coût mesuré d'un run quotidien

Requête (avec SYSADMIN, après `GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE SYSADMIN` par Lucas) :

```sql
SELECT warehouse_name,
       ROUND(SUM(credits_used), 4) AS credits
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE warehouse_name IN ('INGEST_WH', 'TRANSFORM_WH', 'BI_WH')
  AND start_time >= '2026-11-03 00:00'
  AND start_time <  '2026-11-04 00:00'
GROUP BY 1
ORDER BY 2 DESC;
```

Temps de calcul réel par entrepôt, sans attendre le retard des vues de facturation :

```sql
SELECT warehouse_name,
       COUNT(*)                                   AS requetes,
       ROUND(SUM(total_elapsed_time) / 1000, 1)   AS secondes
FROM TABLE(MUTUELLE_FRAUD.INFORMATION_SCHEMA.QUERY_HISTORY(RESULT_LIMIT => 10000))
WHERE warehouse_name IN ('INGEST_WH', 'TRANSFORM_WH', 'BI_WH')
  AND start_time >= '2026-11-03 09:00'
GROUP BY 1;
```

Mesure par heure (03/11). Les créneaux de 09:00 et de 11:00 contiennent chacun 2 `dbt build` (09:50 et 09:57, 11:03 et 11:40, voir `OPS.DBT_RESULTS`). Le créneau de 12:00 n'en contient qu'un :

| Entrepôt | 09:00 (ingestion + 2 dbt) | 10:00 (incident NOEMIE : 3 essais de dbt + tests) | 11:00 (reprise : ingestion + 2 dbt) | 12:00 (1 dbt) | Total du 03/11 |
|---|---|---|---|---|---|
| `INGEST_WH` | 0,0265 | 0,0484 | 0,0257 | 0 | 0,1006 |
| `TRANSFORM_WH` | 0,0840 | 0,1614 | 0,0844 | 0,0451 | 0,3749 |
| `BI_WH` (dashboard) | 0,0002 | 0,0237 | 0,0234 | 0,0243 | 0,0716 |
| **Total** | 0,111 | 0,234 | 0,134 | 0,069 | **0,547** |

**Un run quotidien coûte environ 0,07 crédit** : 0,027 pour l'ingestion (créneau de 09:00) et 0,045 pour un `dbt build` (créneau de 12:00). Une consultation courte du dashboard (environ 90 s d'entrepôt) coûte environ 0,024 crédit.

Un entrepôt XSMALL consomme 1 crédit par heure de fonctionnement, facturé à la seconde avec 60 s minimum à chaque démarrage. Un run qui réveille deux entrepôts quelques minutes coûte donc une petite fraction de crédit.

## 3. Projection sur un an (hypothèses explicites)

| Hypothèse | Valeur |
|---|---|
| Runs par an | 365 (un par matin) |
| Crédits par run | 0,07 (mesuré, section 2) |
| Dashboard | une consultation courte par jour ouvré (250 jours), soit 0,024 crédit par consultation ; une consultation longue coûte plus cher (jusqu'à 1 crédit par heure d'entrepôt allumé) |
| Prix d'un crédit | **3 $ (hypothèse, ordre de grandeur Standard / Enterprise ; à remplacer par le prix réel du contrat)** |

| Poste | Crédits par an | Coût par an |
|---|---|---|
| Pipeline (365 × 0,07) | 26 | 78 $ |
| Dashboard (250 × 0,024) | 6 | 18 $ |
| **Total entrepôts** | **32** | **≈ 100 $** |

Le compute pool du dashboard s'ajoute à ce total (section 1). On le maîtrise en arrêtant l'application quand elle ne sert pas.

Par mois, cela fait moins de **3 crédits**, très loin du quota de 20 du resource monitor. À comparer à l'enjeu : l'objectif est de bloquer environ **0,5 M€ de fraude optique par an**, soit plus de 5 000 fois le coût du pipeline.

Ce qui ferait monter le coût : un volume ×100 (mutuelle nationale), un dashboard en accès direct très consulté, ou un passage au temps réel. On resterait sur des XSMALL, sauf si `dbt build` dépassait quelques minutes.

## 4. Garde-fou budget

Resource monitor `MUTUELLE_MONITOR` (créé à la main par ACCOUNTADMIN dans `terraform/bootstrap_admin.sql`, puis rattaché aux 3 entrepôts) :

| Seuil | Action |
|---|---|
| 50 % de 20 crédits par mois | e-mail aux administrateurs |
| 80 % | e-mail |
| 100 % | **les 3 entrepôts sont suspendus** |

Vérification du 04/11 : `SHOW RESOURCE MONITORS LIKE 'MUTUELLE_MONITOR';` → **0,72 crédit consommé sur 20** depuis le 02/11, pour toute la construction, les tests, les incidents et les répétitions. Alertes à 50 % et 80 %, arrêt à 100 %, niveau WAREHOUSE.

Terraform ignore volontairement ce rattachement (`ignore_changes` dans le module warehouse) : un `apply` ne le retire jamais.

Limite : le resource monitor ne surveille que les entrepôts. Le compute pool du dashboard n'est pas plafonné. On le maîtrise en arrêtant l'application quand on ne s'en sert pas, et en suivant sa consommation dans Snowsight (Admin → Cost Management).

## 5. Procédure d'arrêt et de nettoyage (après la note)

1. **Arrêter le pipeline** : mettre le DAG en pause dans Airflow, puis `docker compose down` dans `airflow/`, et `docker compose -f docker-compose.crm.yml down` à la racine.
2. **Arrêter le dashboard** : supprimer l'application Streamlit `DASHBOARD_ANTI_FRAUDE`, pour que le compute pool ne consomme plus.
3. **Supprimer la plateforme** : `cd terraform && terraform destroy`. Cela supprime la base, les 3 entrepôts, les rôles et les comptes de service.
4. **Nettoyer les étapes manuelles** (ACCOUNTADMIN) : `DROP USER SVC_TERRAFORM; DROP USER CLEMENT; DROP USER ELIOTT; DROP RESOURCE MONITOR MUTUELLE_MONITOR;`
5. **Révoquer les secrets** : supprimer le webhook Discord, le workspace HCP `mutuelle-fraud` et les clés dans `~/keys/`.
6. **Vérifier** : `SHOW WAREHOUSES;` et `SHOW DATABASES LIKE 'MUTUELLE_FRAUD';` ne renvoient plus rien.

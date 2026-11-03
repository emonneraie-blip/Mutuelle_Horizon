# FinOps · coûts du prototype (owner : Eliott)

Principe : on paie seulement le calcul réellement utilisé, on le voit par usage, et un garde-fou coupe tout avant une mauvaise surprise.

> Les valeurs `[À REMPLIR]` viennent du test réel (E2). Les vues `ACCOUNT_USAGE` ont jusqu'à 3 h de retard : lancer les requêtes au moins 3 h après le run.

## 1. Ce qui coûte, et ce qui est gratuit

| Composant | Coût | Pourquoi |
|---|---|---|
| Snowflake : 3 entrepôts XSMALL | crédits, seulement quand un entrepôt tourne | arrêt automatique après 60 s, démarrage à la demande, suspendus à la création |
| Snowflake : stockage | négligeable (quelques Mo) | quelques milliers de lignes par jour |
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
  AND start_time >= '[À REMPLIR : début du run, ex. 2026-11-03 18:00]'
  AND start_time <  '[À REMPLIR : fin du run + 1 h]'
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
  AND start_time >= '[À REMPLIR : début du run]'
GROUP BY 1;
```

| Entrepôt | Crédits pour 1 run | Durée de la tâche Airflow |
|---|---|---|
| `INGEST_WH` | [À REMPLIR] | [À REMPLIR] |
| `TRANSFORM_WH` | [À REMPLIR] | [À REMPLIR] |
| `BI_WH` (consultation du dashboard) | [À REMPLIR] | — |
| **Total** | **[À REMPLIR]** | **run complet : [À REMPLIR]** |

Un entrepôt XSMALL consomme 1 crédit par heure de fonctionnement, facturé à la seconde avec 60 s minimum à chaque démarrage. Un run qui réveille deux entrepôts quelques minutes coûte donc une petite fraction de crédit.

## 3. Projection sur un an (hypothèses explicites)

| Hypothèse | Valeur |
|---|---|
| Runs par an | 365 (un par matin) |
| Crédits par run | [À REMPLIR, section 2] |
| Prix d'un crédit | [À REMPLIR : prix de l'édition et de la région du compte, Snowsight > Admin > Cost Management] |
| Consultation du dashboard | [À REMPLIR] min par jour sur `BI_WH` |

Coût annuel ≈ 365 × crédits par run × prix d'un crédit = **[À REMPLIR] € par an**.

À comparer à l'enjeu : l'objectif est de bloquer environ **0,5 M€ de fraude optique par an**. Le pipeline coûte donc [À REMPLIR] fois moins que ce qu'il doit faire économiser.

Ce qui ferait monter le coût : un volume ×100 (mutuelle nationale), un dashboard en accès direct très consulté, ou un passage au temps réel. On resterait sur des XSMALL, sauf si `dbt build` dépassait quelques minutes.

## 4. Garde-fou budget

Resource monitor `MUTUELLE_MONITOR` (créé à la main par ACCOUNTADMIN dans `terraform/bootstrap_admin.sql`, puis rattaché aux 3 entrepôts) :

| Seuil | Action |
|---|---|
| 50 % de 20 crédits par mois | e-mail aux administrateurs |
| 80 % | e-mail |
| 100 % | **les 3 entrepôts sont suspendus** |

Vérification : `SHOW RESOURCE MONITORS LIKE 'MUTUELLE_MONITOR';` → [À REMPLIR : crédits consommés / quota].

Terraform ignore volontairement ce rattachement (`ignore_changes` dans le module warehouse) : un `apply` ne le retire jamais.

## 5. Procédure d'arrêt et de nettoyage (après la note)

1. **Arrêter le pipeline** : mettre le DAG en pause dans Airflow, puis `docker compose down` dans `airflow/`, et `docker compose -f docker-compose.crm.yml down` à la racine.
2. **Supprimer la plateforme** : `cd terraform && terraform destroy`. Cela supprime la base, les 3 entrepôts, les rôles et les comptes de service.
3. **Nettoyer les étapes manuelles** (ACCOUNTADMIN) : `DROP USER SVC_TERRAFORM; DROP USER CLEMENT; DROP USER ELIOTT; DROP RESOURCE MONITOR MUTUELLE_MONITOR;`
4. **Révoquer les secrets** : supprimer le webhook Discord, le workspace HCP `mutuelle-fraud` et les clés dans `~/keys/`.
5. **Vérifier** : `SHOW WAREHOUSES;` et `SHOW DATABASES LIKE 'MUTUELLE_FRAUD';` ne renvoient plus rien.

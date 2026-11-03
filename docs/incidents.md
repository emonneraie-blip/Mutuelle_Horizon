# Incidents · fiabilité du pipeline (owner : Eliott, avec Lucas et Clément)

Deux incidents réels, rejoués par le pipeline lui-même et documentés avec leurs preuves. Le DAG traite chaque matin le lot de la veille, avec 2 relances par tâche et une alerte Discord après le dernier échec.

> Les valeurs `[À REMPLIR]` et les captures viennent du backfill Airflow sur la machine de démo (dates logiques du 27/10 au 04/11).

## Incident 1 · Relance d'un lot déjà chargé (aucun double comptage)

| | |
|---|---|
| **Scénario** | Une tâche plante après avoir écrit, ou quelqu'un relance un jour déjà traité. Sans protection, les factures seraient comptées deux fois et le montant à risque doublerait, alors que tout resterait vert. |
| **Protection** | `COPY INTO` ne recharge jamais un fichier déjà chargé. Le CRM passe par un `MERGE` sur la clé. dbt reconstruit silver et gold à partir de BRONZE. |
| **Comment le rejouer** | Dans Airflow, relancer (Clear) le run du [À REMPLIR : ex. 03/11], ou `run jobs.run_day --date 2026-10-27 --simulate-crm`. |
| **Résultat attendu** | `ALREADY_LOADED`, 0 ligne chargée, `MERGE: 0 inserted, 0 updated`. Les comptes de BRONZE et le KPI du jour sont identiques avant et après. |
| **Preuve** | [À REMPLIR : capture des logs `ingest_factures` et de `LOAD_AUDIT`] |

Contrôle avant / après :

```sql
SELECT COUNT(*), COUNT(DISTINCT ID_DEMANDE) FROM MUTUELLE_FRAUD.BRONZE.FACTURES_OPTIQUE;
SELECT * FROM MUTUELLE_FRAUD.GOLD.KPI_FRAUDE_QUOTIDIEN WHERE batch_date = '[À REMPLIR]';
```

| | Avant | Après la relance |
|---|---|---|
| Lignes de factures | [À REMPLIR] | [À REMPLIR : identique] |
| Montant à risque du jour | [À REMPLIR] | [À REMPLIR : identique] |

## Incident 2 · Décomptes NOEMIE en retard (le 30/10)

| | |
|---|---|
| **Scénario** | Le fichier NOEMIE de la Sécurité sociale n'arrive pas le 30/10. Sans contrôle, la règle F2 (« facture sans décompte ») signalerait toutes les factures du jour : une avalanche de faux positifs pour les gestionnaires. |
| **Détection** | `load_noemie` enregistre `NO_FILE` (avertissement, pas d'échec). Le test dbt `assert_lot_noemie_present` échoue. |
| **Effet** | `dbt build` s'arrête avant gold : la liste à contrôler n'est pas publiée, et celle de la veille reste en place. La tâche `dbt_build` échoue après 2 relances, et **une alerte part sur Discord**. |
| **Reprise** | Le 31/10, le fichier arrive avec les décomptes des deux jours. Le run suivant repasse au vert sans intervention. Grâce au délai de grâce de 2 jours de F2, aucune facture n'est signalée F2 à tort. |
| **Preuve** | [À REMPLIR : capture du run rouge du 30/10 et du run vert du 31/10 dans Airflow, de l'alerte Discord, et du résultat du test dbt] |

| Lot | Run Airflow | Durée | Résultat |
|---|---|---|---|
| 30/10 | [À REMPLIR] | [À REMPLIR] | rouge : `dbt_build` en échec, gold non publié, alerte Discord |
| 31/10 | [À REMPLIR] | [À REMPLIR] | vert : rattrapage, [À REMPLIR] décomptes chargés |

## Bonus · Changement de schéma des factures (si on nous le demande)

Une nouvelle colonne apparaît dans le CSV. `load_invoices` s'arrête **avant** de charger, avec le statut `SCHEMA_DRIFT` dans `LOAD_AUDIT` : rien n'est écrit, et on adapte le contrat avant de relancer. À rejouer sur un jeu de test : `generate.py --schema-drift-from 2026-10-31`.

## Ce qu'on ferait en production

- Une alerte sur la fraîcheur des sources (fichier attendu à 05:00, absent à 05:30), avant même le run de 06:00.
- Un tableau de bord des runs (durée, lignes chargées, tests en échec) à partir de `LOAD_AUDIT` et des résultats dbt.
- Un ticket automatique dans l'outil de l'équipe à chaque alerte, pas seulement un message Discord.

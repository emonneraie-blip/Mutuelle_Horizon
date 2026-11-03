# Incidents · fiabilité du pipeline (owner : Eliott, avec Lucas et Clément)

Deux incidents réels, rejoués par le pipeline lui-même et documentés avec leurs preuves. Le DAG traite chaque matin le lot de la veille, avec 2 relances par tâche et une alerte Discord après le dernier échec.

> Testés en réel le 03/11 sur la machine de démo (Airflow + Snowflake). Run complet : 6 tâches, **1 min 02 s** (`preuves/run_vert.png`).

## Incident 1 · Relance d'un lot déjà chargé (aucun double comptage)

| | |
|---|---|
| **Scénario** | Une tâche plante après avoir écrit, ou quelqu'un relance un jour déjà traité. Sans protection, les factures seraient comptées deux fois et le montant à risque doublerait, alors que tout resterait vert. |
| **Protection** | `COPY INTO` ne recharge jamais un fichier déjà chargé. Le CRM passe par un `MERGE` sur la clé. dbt reconstruit silver et gold à partir de BRONZE. |
| **Comment le rejouer** | Relancer dans Airflow un jour déjà chargé. Testé avec le run planifié du 03/11 06:00, qui retraite le lot du 02/11. |
| **Résultat attendu** | `ALREADY_LOADED`, 0 ligne chargée, `MERGE: 0 inserted, 0 updated`. Les comptes de BRONZE et le KPI du jour sont identiques avant et après. |
| **Preuve** | `preuves/incident1_already_loaded.png` : `batch 2026-11-02: 0 file(s), 0 rows loaded (ALREADY_LOADED); rows in file(s): 185`, tâche en 5,8 s, run vert |

Contrôle (à relancer avant et après une relance) :

```sql
SELECT COUNT(*), COUNT(DISTINCT ID_DEMANDE) FROM MUTUELLE_FRAUD.BRONZE.FACTURES_OPTIQUE;
SELECT * FROM MUTUELLE_FRAUD.GOLD.KPI_FRAUDE_QUOTIDIEN ORDER BY batch_date DESC;
```

## Incident 2 · Décomptes NOEMIE en retard (le 30/10)

| | |
|---|---|
| **Scénario** | Le fichier NOEMIE de la Sécurité sociale n'arrive pas le 30/10. Sans contrôle, la règle F2 (« facture sans décompte ») signalerait toutes les factures du jour : une avalanche de faux positifs pour les gestionnaires. |
| **Détection** | `load_noemie` enregistre `NO_FILE` (avertissement, pas d'échec). Le test dbt `assert_lot_noemie_present` échoue. |
| **Effet** | `dbt build` s'arrête avant gold : la liste à contrôler n'est pas publiée, et celle de la veille reste en place. La tâche `dbt_build` échoue après 2 relances, et **une alerte part sur Discord**. |
| **Reprise** | Le 31/10, le fichier arrive avec les décomptes des deux jours. Le run suivant repasse au vert sans intervention. Grâce au délai de grâce de 2 jours de F2, aucune facture n'est signalée F2 à tort. |
| **Preuve** | `preuves/incident2_dbt_build_echec.png` : `Failure in test assert_lot_noemie_present`, `PASS=31 ERROR=1 SKIP=15` (les 15 modèles et tests de gold sont sautés), 3 essais de 40 s. `preuves/incident2_alerte_discord.png` : « tâche dbt_build en échec pour le lot du 2026-10-30 (run du 2026-10-31, essai 3) », reçue à 10:56. Run vert du 31/10 : [À REMPLIR pendant le backfill] |

| Lot | Run Airflow | Durée | Résultat |
|---|---|---|---|
| 30/10 | Trigger manuel, date logique 31/10 (03/11, 10:50, heure de Paris) | `dbt_build` : 3 × 40 s | rouge : `NO_FILE`, test de complétude en échec, gold non publié, alerte Discord |
| 31/10 | [À REMPLIR pendant le backfill] | [À REMPLIR] | vert : rattrapage des décomptes des deux jours |

## Bonus · Changement de schéma des factures (si on nous le demande)

Une nouvelle colonne apparaît dans le CSV. `load_invoices` s'arrête **avant** de charger, avec le statut `SCHEMA_DRIFT` dans `LOAD_AUDIT` : rien n'est écrit, et on adapte le contrat avant de relancer. À rejouer sur un jeu de test : `generate.py --schema-drift-from 2026-10-31`.

## Ce qu'on ferait en production

- Une alerte sur la fraîcheur des sources (fichier attendu à 05:00, absent à 05:30), avant même le run de 06:00.
- Un tableau de bord des runs (durée, lignes chargées, tests en échec) à partir de `LOAD_AUDIT` et des résultats dbt.
- Un ticket automatique dans l'outil de l'équipe à chaque alerte, pas seulement un message Discord.

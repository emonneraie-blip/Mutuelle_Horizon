# Démo live du jeudi 05/11 · le run du lot du 04/11

## Le seul geste à faire : retirer la pause

Le jour de la démo, on lance le pipeline en **retirant la pause** du DAG `mutuelle_fraud_daily` (interrupteur à côté du nom). On **ne clique pas sur « Déclencher »**.

Pourquoi (testé le 03/11 sur Airflow 3.3.2) :

| Constat | Conséquence |
|---|---|
| Retirer la pause crée tout seul le run planifié du jour (`scheduled__2026-11-05T05:00:00+00:00`, soit 06:00 à Paris), qui traite la **veille** | Le jeudi 05/11, retirer la pause lance exactement le lot du 04/11 |
| « Déclencher » coche par défaut « Réactiver le DAG lors du déclenchement » | Un clic sur Déclencher crée **deux** runs sur le même lot : le manuel et le planifié |
| Un run déclenché alors que le DAG est en pause reste « En file » et ne démarre pas | Un clic sur Déclencher en pause, oublié, partirait au moment où l'on retire la pause |

## Avant la démo (jeudi matin)

1. Le DAG est **en pause** depuis mercredi soir, donc aucun run n'est parti à 06:00.
2. Onglet **Runs** : **aucun run « En file »**. S'il y en a un, le supprimer (icône corbeille).
3. Le dernier run vert traite le lot du 03/11.
4. **Ouvrir le dashboard** (Snowsight → Streamlit, `DASHBOARD_ANTI_FRAUDE`) avant le début de l'oral : il affiche le lot du 03/11.

## Pendant la démo

1. Retirer la pause, ce qui fait apparaître le run `scheduled__2026-11-05…`.
2. Ouvrir la vue graphe : les 6 tâches passent au vert en environ 1 minute.
3. Montrer dans les logs de `ingest_factures` la ligne `batch 2026-11-04` : le lot de la veille.
4. **Relance sans doublon (incident 1 en direct)** : sur le run vert, relancer `ingest_factures` (Clear). Le log affiche `ALREADY_LOADED`, 0 ligne.
5. Attendre **1 minute** (le cache du dashboard dure 60 s), puis rafraîchir le dashboard : il affiche le lot du 04/11, avec la F5 du jour.
6. **Remettre la pause.**

## Si le run ne part pas dans la minute

Ouvrir « Déclencher », mettre la date logique **2026-11-05 06:00**, laisser cochée « Réactiver lors du déclenchement », puis valider. En dernier recours, on passe la vidéo de la répétition.

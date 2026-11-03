# dashboard/ · owner Clément

Application Streamlit in Snowflake du gestionnaire anti-fraude. Elle lit uniquement GOLD :
les factures à contrôler du lot, les règles déclenchées, les KPI et la date de fraîcheur.

L'application est déployée dans `MUTUELLE_FRAUD.GOLD` : Snowsight > Projects > Streamlit > `DASHBOARD_ANTI_FRAUDE`.
Rôle `TRANSFORM_ROLE`, entrepôt `BI_WH`, compute pool `SYSTEM_COMPUTE_POOL_CPU`. Le code se met à jour depuis le Workspace `DASHBOARD_ANTI_FRAUDE`, puis Deploy.

Avant une démo : cliquer sur Start (environ 1 minute de démarrage). Après : menu à côté de Active > End session, pour ne plus consommer de crédits.
L'application tourne avec les droits de son propriétaire : `ANALYST_ROLE` ne lit toujours que `KPI_FRAUDE_QUOTIDIEN`.

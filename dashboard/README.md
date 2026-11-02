# dashboard/ · owner Clément

Application Streamlit in Snowflake du gestionnaire anti-fraude. Elle lit uniquement GOLD :
les factures à contrôler du lot, les règles déclenchées, les KPI et la date de fraîcheur.

Déploiement : Snowsight > Projects > Streamlit > + Streamlit App, rôle `TRANSFORM_ROLE`, entrepôt `BI_WH`,
base `MUTUELLE_FRAUD`, schéma `GOLD`, puis coller `streamlit_app.py`.
L'application tourne avec les droits de son propriétaire : `ANALYST_ROLE` ne lit toujours que `KPI_FRAUDE_QUOTIDIEN`.

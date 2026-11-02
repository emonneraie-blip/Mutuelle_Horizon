# transformation/ · owner Clément

dbt project `mutuelle_dbt` (BRONZE → SILVER → GOLD + OPS.DBT_RESULTS) and its Dockerfile → image `fraud-dbt:1.0.0`
(the dbt project is COPIED into the image; dbt-core / dbt-snowflake 1.11.x pinned).
Contract with the ingestion layer: `docs/contracts.md`. Executable spec of the cleaning and of the 7 rules: `data_generator/validate.py`.
Runs as `SVC_TRANSFORM` / `TRANSFORM_ROLE` / `TRANSFORM_WH`, key mounted read-only on `/secrets/svc_transform.p8`.

# fraud-dbt : lance le projet dbt (BRONZE -> SILVER -> GOLD)
# Build : docker build -t fraud-dbt:1.0.0 transformation/
# Run   : docker run --rm --env-file .env -e SNOWFLAKE_USER=SVC_TRANSFORM -e SNOWFLAKE_ROLE=TRANSFORM_ROLE \
#           -e SNOWFLAKE_WAREHOUSE=TRANSFORM_WH -e SNOWFLAKE_PRIVATE_KEY_FILE=/secrets/svc_transform.p8 \
#           -e NIR_SALT -v "$HOME/keys/mutuelle:/secrets:ro" \
#           fraud-dbt:1.0.0 dbt build --vars '{batch_date: 2026-11-03}'
FROM python:3.12.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 DBT_PROFILES_DIR=/app

WORKDIR /app

# 1. Les dépendances d'abord : cette couche reste en cache tant que requirements.txt ne change pas
COPY requirements.txt .
RUN pip install -r requirements.txt

# 2. Puis le projet dbt, COPIÉ dans l'image (le bug de l'image fournie au TD Airflow)
COPY . .

# 3. Jamais en root. La clé est montée au lancement, jamais copiée dans l'image.
RUN useradd --create-home --uid 10002 dbt && chown -R dbt /app
USER dbt

LABEL org.opencontainers.image.title="fraud-dbt" org.opencontainers.image.version="1.0.0"
CMD ["dbt", "build"]

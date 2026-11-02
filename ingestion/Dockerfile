# fraud-ingest: ingestion jobs of the Mutuelle Horizon Santé fraud platform (sources -> BRONZE)
# Build:  docker build -t fraud-ingest:1.0.0 ingestion/
# Run:    docker run --rm --env-file .env -v "$PWD/data:/data" -v "$HOME/keys:/secrets:ro" \
#           fraud-ingest:1.0.0 python -m jobs.load_invoices --date 2026-10-27
FROM python:3.12.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/data

WORKDIR /app

# 1. dependencies first (cached layer), every version pinned
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. then the code
COPY jobs/ jobs/
COPY sql/ sql/

# 3. never run as root; secrets are mounted at run time (/secrets), never copied into the image
RUN useradd --create-home --uid 10001 ingest && mkdir -p /data && chown ingest /data
USER ingest

LABEL org.opencontainers.image.title="fraud-ingest" org.opencontainers.image.version="1.0.0"
CMD ["python", "-c", "print('fraud-ingest 1.0.0 - run: python -m jobs.<job> --help')"]

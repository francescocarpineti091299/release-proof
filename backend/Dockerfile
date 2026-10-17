# syntax=docker/dockerfile:1.7
# ReleaseProof API (FastAPI + orchestrator + SQLite store).
# Build context = repository root:
#   docker build -f backend/Dockerfile -t releaseproof/api:0.1.0 .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first (cached until pyproject.toml changes); the package itself runs from source.
COPY backend/pyproject.toml /app/backend/pyproject.toml
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('/app/backend/pyproject.toml', 'rb'))['project']['dependencies']))" > /tmp/requirements.txt \
 && pip install -r /tmp/requirements.txt \
 && rm /tmp/requirements.txt

COPY backend/releaseproof /app/backend/releaseproof
COPY contract /app/contract
COPY profiles /app/profiles
COPY reference /app/reference

# Non-root user. /data is created here so a fresh named volume inherits this ownership
# (compose starts the api before the runners for that reason).
RUN useradd --uid 10001 --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin rp \
 && mkdir -p /data \
 && chown rp:rp /data

ENV PYTHONPATH=/app/backend \
    RELEASEPROOF_ENV=demo \
    RELEASEPROOF_DATA_DIR=/data \
    RELEASEPROOF_RUNNER_DATA_DIR=/data \
    RELEASEPROOF_CONTRACT_DIR=/app/contract/PQC_Engineering_Pack_V1_2 \
    RELEASEPROOF_REFERENCE_DIR=/app/reference/wp0-freeze-20261001 \
    RELEASEPROOF_PROFILES_DIR=/app/profiles

USER rp
EXPOSE 8000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

# Exactly one worker: the API process is the single SQLite writer and owns the in-memory queue.
CMD ["uvicorn", "releaseproof.api.app:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*", \
     "--timeout-graceful-shutdown", "10"]

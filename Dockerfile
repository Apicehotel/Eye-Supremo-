# Eye Supremo online: UN solo container con API FastAPI + frontend React.
# Il backend serve gia' frontend/dist sulla stessa origine, quindi niente CORS
# e niente VITE_EYE_API_URL. Dati (SQLite, upload, backup) nel volume /data.
# Vedi docs/DEPLOY_ONLINE.md.

# ---- 1) build del frontend ----
FROM node:22-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 2) runtime Python ----
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EYESUPREMO_DATA_DIR=/data
WORKDIR /app

COPY backend/requirements-server.txt backend/requirements-server.txt
RUN pip install --no-cache-dir -r backend/requirements-server.txt

COPY backend/ backend/
COPY --from=frontend /build/frontend/dist frontend/dist

RUN useradd --create-home --uid 10001 eyesupremo \
    && mkdir -p /data \
    && chown -R eyesupremo:eyesupremo /data /app
USER eyesupremo

VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

# Una sola istanza/worker: SQLite in WAL e cache in memoria non vanno condivisi.
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

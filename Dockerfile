# Single-service image: React dashboard + FastAPI API on one port.
# The simulated dataset, SQLite database and monthly reports are built at image
# build time, so the running container needs little memory (~200 MB).

# ---- 1. Build the React dashboard ------------------------------------------
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

# ---- 2. Python runtime + data -------------------------------------------------
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    WTA_STATIC_DIR=/app/frontend/dist \
    WTA_DEMO_MODE=1
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend backend
COPY scripts scripts
COPY sql sql
RUN mkdir -p data reports powerbi/datasets \
 && python scripts/generate_data.py \
 && python scripts/run_pipeline.py \
 && python scripts/generate_reports.py \
 && rm -f data/generated/*.csv data/processed/scada_clean.csv
COPY --from=web /web/dist frontend/dist
EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --app-dir backend"]

# Backend: FastAPI + engine. Runs migrations and seeds an empty database on start.
# Build context is the repo root (docker-compose.yml / render.yaml) so the kit data can be copied in.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 KIT_ROOT=/app
WORKDIR /app/backend

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/engine ./engine
COPY backend/api ./api
COPY backend/services ./services
COPY backend/db ./db
COPY backend/seed ./seed
COPY backend/alembic.ini .
COPY master_data /app/master_data
COPY contracts /app/contracts
COPY pr_batches /app/pr_batches

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m seed.load --if-empty && uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

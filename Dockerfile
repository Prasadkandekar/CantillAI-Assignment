# Backend: FastAPI + engine. Runs migrations and seeds an empty database on start.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY engine ./engine
COPY api ./api
COPY services ./services
COPY db ./db
COPY seed ./seed
COPY master_data ./master_data
COPY contracts ./contracts
COPY pr_batches ./pr_batches
COPY alembic.ini .

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m seed.load --if-empty && uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

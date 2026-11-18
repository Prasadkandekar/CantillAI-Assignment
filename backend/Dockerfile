# Backend: FastAPI + engine. Runs migrations on start and seeds an empty database.
# Build context is the backend/ folder (Render: Root Directory = backend, Dockerfile Path = ./Dockerfile).
# Local: docker build -t corvo-backend backend
# The kit data (master_data/contracts/pr_batches) is NOT in the image: the database (Neon) is seeded once
# from a machine that has the CSVs, so `seed.load --if-empty` is a no-op here.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m seed.load --if-empty && uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY alembic.ini ./alembic.ini

ENV PYTHONPATH=/app

# Run Alembic migrations (or stamp for legacy DBs) then exec uvicorn.
# To skip the migrate step for one-off invocations (e.g. running a
# Celery worker from the same image), override CMD or set
# TG_SERVE_CMD to a non-uvicorn command.
CMD ["python", "-m", "backend.migrate_then_serve"]

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Build deps for the C extensions opentele pulls in (tgcrypto). Removed
# after pip install so the runtime image doesn't carry the compiler.
COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc python3-dev libffi-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove gcc python3-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend ./backend
COPY alembic.ini ./alembic.ini

ENV PYTHONPATH=/app

# Run Alembic migrations (or stamp for legacy DBs) then exec uvicorn.
# To skip the migrate step for one-off invocations (e.g. running a
# Celery worker from the same image), override CMD or set
# TG_SERVE_CMD to a non-uvicorn command.
CMD ["python", "-m", "backend.migrate_then_serve"]

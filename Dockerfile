FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Build deps for the C extensions opentele pulls in (tgcrypto). They're
# purged after install so the runtime image stays lean. Runtime libs
# (libglib2.0-0 = libgthread; libxkbcommon0 + libgl1 for PyQt5 used by
# opentele's binary parser) MUST stay installed.
COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc python3-dev libffi-dev \
        libglib2.0-0 libxkbcommon0 libgl1 libdbus-1-3 libfontconfig1 \
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

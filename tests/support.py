"""Shared test helpers. Imported before any backend module so env tweaks
take effect (test engine, no auto table creation on app startup, etc.).

Backend selection is controlled by `TEST_DB_BACKEND`:
  - unset / "sqlite" — in-memory SQLite via StaticPool (default; local dev)
  - "mariadb"        — connect to a real MariaDB using the MYSQL_* env
                       vars (used by the CI matrix to catch SQLite vs
                       MariaDB dialect drift — JSON, SELECT FOR UPDATE,
                       case-sensitivity, etc.)
"""
from __future__ import annotations

import os

os.environ.setdefault("AUTO_CREATE_TABLES", "false")
os.environ.setdefault("AUTO_MIGRATE_COLUMNS", "false")
os.environ.setdefault("APP_SECRET", "test-secret-please-do-not-use-in-prod")
os.environ.setdefault("APP_JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("APP_JWT_TTL_MINUTES", "60")

import sqlalchemy
from sqlalchemy.orm import sessionmaker

from backend.app.core import database as db_module
from backend.app.core.database import Base


_installed: dict[str, object] = {}


def _make_sqlite_engine():
    return sqlalchemy.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        future=True,
        # Single shared connection so all SessionLocal() handles see
        # the same schema and rows.
        poolclass=sqlalchemy.pool.StaticPool,
    )


def _make_mariadb_engine():
    # Late import so app config picks up any MYSQL_* env vars the CI sets.
    from backend.app.core.config import settings
    return sqlalchemy.create_engine(
        settings.database_url, pool_pre_ping=True, future=True,
    )


def install_sqlite_session() -> sessionmaker:
    """Return a sessionmaker for the active test backend.

    Name kept for back-compat; the function returns SQLite by default and
    a real MariaDB session when `TEST_DB_BACKEND=mariadb` is exported.
    All tests call this once; the engine is cached for the process.
    """
    if "SessionLocal" in _installed:
        return _installed["SessionLocal"]  # type: ignore[return-value]

    backend = os.environ.get("TEST_DB_BACKEND", "sqlite").lower()
    if backend == "mariadb":
        engine = _make_mariadb_engine()
    else:
        engine = _make_sqlite_engine()

    import backend.app.models  # noqa: F401  populate metadata

    # Drop-and-recreate for a clean slate. On SQLite (in-memory) drop_all
    # is a no-op the first time; on MariaDB it wipes any leftover tables
    # from a prior CI run (matters when re-runs use the same service
    # container).
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db_module.engine = engine
    db_module.SessionLocal = SessionLocal
    _installed["engine"] = engine
    _installed["SessionLocal"] = SessionLocal
    return SessionLocal

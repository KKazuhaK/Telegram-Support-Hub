"""Shared test helpers. Imported before any backend module so env tweaks
take effect (sqlite engine, no auto table creation on app startup, etc.)."""
from __future__ import annotations

import os

os.environ.setdefault("AUTO_CREATE_TABLES", "false")
os.environ.setdefault("APP_SECRET", "test-secret-please-do-not-use-in-prod")
os.environ.setdefault("APP_JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("APP_JWT_TTL_MINUTES", "60")

import sqlalchemy
from sqlalchemy.orm import sessionmaker

from backend.app.core import database as db_module
from backend.app.core.database import Base


_installed: dict[str, object] = {}


def install_sqlite_session() -> sessionmaker:
    """Reuse a single in-memory SQLite engine for the whole test process so
    every test module shares the same DB state. Re-running create_all is a
    no-op once tables exist."""
    if "SessionLocal" in _installed:
        return _installed["SessionLocal"]  # type: ignore[return-value]

    engine = sqlalchemy.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        future=True,
        # use a single shared connection so all SessionLocal() handles see
        # the same schema and rows
        poolclass=sqlalchemy.pool.StaticPool,
    )

    import backend.app.models  # noqa: F401  populate metadata
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db_module.engine = engine
    db_module.SessionLocal = SessionLocal
    _installed["engine"] = engine
    _installed["SessionLocal"] = SessionLocal
    return SessionLocal

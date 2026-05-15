from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_db_and_tables() -> None:
    settings.ensure_directories()
    from backend.app.models import (  # noqa: F401
        account, agent, audit, campaign, customer, data_groups,
        message, proxy, template, tenant,
    )

    Base.metadata.create_all(bind=engine)

    if settings.auto_migrate_columns:
        import logging
        from backend.app.core.schema_sync import ensure_columns_present
        added = ensure_columns_present(engine, Base.metadata)
        if added:
            logging.getLogger(__name__).info(
                "schema-sync added %d columns: %s", len(added), added,
            )

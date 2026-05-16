"""Alembic environment hook.

Pulls the database URL from `backend.app.core.config.settings` so the
same env vars (MYSQL_HOST / MYSQL_USER / ...) that run the app also
drive migrations. Importing `backend.app.models` populates
`Base.metadata` so autogenerate sees every table.
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.app.core.config import settings
from backend.app.core.database import Base
import backend.app.models  # noqa: F401  populates Base.metadata


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the URL from alembic.ini with the app's runtime URL. -x url=...
# still wins (CLI arg) for one-off targets.
#
# CRITICAL: `str(URL_object)` masks the password as '***' as a leak-prevention
# default. Alembic would then try to connect with literal "***" and fail
# with "Access denied (using password: YES)". Use render_as_string(
# hide_password=False) to keep the real password in the URL string.
cli_url = context.get_x_argument(as_dictionary=True).get("url")
if cli_url:
    config.set_main_option("sqlalchemy.url", cli_url)
else:
    db_url = settings.database_url
    # SQLAlchemy URL exposes the real password via render_as_string;
    # plain str() returns a masked version.
    config.set_main_option(
        "sqlalchemy.url",
        db_url.render_as_string(hide_password=False) if hasattr(db_url, "render_as_string") else str(db_url),
    )

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Render SQL to stdout without a live DB — useful for review."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # compare_type=True so changing String(120) → String(200) shows
            # up in autogenerate diffs; otherwise type changes are ignored.
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

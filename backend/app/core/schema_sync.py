"""Best-effort schema migration helper.

`Base.metadata.create_all()` only creates *new* tables. When a column is
added to an existing model after the first deploy, nothing in production
adds it for you — every list endpoint that selects the new column starts
returning 500 with `Unknown column ...`.

This module bridges that gap for the simple case "I added some columns,
please ALTER TABLE ADD COLUMN them". It deliberately does **not**:

- drop or rename columns (those need human review)
- alter existing column types
- add or drop indexes / FKs / constraints other than NOT NULL + DEFAULT

For anything beyond pure additions, use Alembic.
"""

from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import MetaData, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import Column

logger = logging.getLogger(__name__)


def _format_default(column: Column) -> str:
    """Return ` DEFAULT ...` clause for the column, or '' if none. Only
    handles constant Python scalar defaults; expression / callable defaults
    are ignored so we don't generate dialect-specific SQL we can't quote."""
    if column.server_default is not None:
        text_obj = getattr(column.server_default, "arg", None)
        if hasattr(text_obj, "text"):
            return f" DEFAULT {text_obj.text}"
        if isinstance(text_obj, str):
            return f" DEFAULT '{text_obj}'"
    if column.default is None:
        return ""
    arg = getattr(column.default, "arg", None)
    if arg is None or callable(arg):
        return ""
    if isinstance(arg, bool):
        return f" DEFAULT {1 if arg else 0}"
    if isinstance(arg, (int, float)):
        return f" DEFAULT {arg}"
    if isinstance(arg, str):
        # Naive quoting is safe here because the value is hard-coded in
        # Python source by the developer, not user input.
        escaped = arg.replace("'", "''")
        return f" DEFAULT '{escaped}'"
    return ""


def _compile_add_column(engine: Engine, column: Column) -> str:
    """Render `<name> <TYPE> [NOT NULL] [DEFAULT ...]` for ALTER TABLE ADD."""
    type_sql = column.type.compile(dialect=engine.dialect)
    nullable = "" if column.nullable else " NOT NULL"
    default = _format_default(column)
    return f"{column.name} {type_sql}{nullable}{default}"


def ensure_columns_present(engine: Engine, metadata: MetaData) -> list[tuple[str, str]]:
    """Add any columns declared in `metadata` but missing in the live DB.

    Returns a list of `(table_name, column_name)` tuples that were added.
    Tables that don't exist yet are skipped — `Base.metadata.create_all()`
    handles those on the same lifespan tick.
    """
    inspector = inspect(engine)
    added: list[tuple[str, str]] = []
    with engine.begin() as conn:
        for table_name, table in metadata.tables.items():
            if not inspector.has_table(table_name):
                continue
            live_cols = {c["name"] for c in inspector.get_columns(table_name)}
            missing: Iterable[Column] = [c for c in table.columns if c.name not in live_cols]
            for column in missing:
                clause = _compile_add_column(engine, column)
                stmt = f"ALTER TABLE {table_name} ADD COLUMN {clause}"
                logger.info("schema-sync: %s", stmt)
                conn.execute(text(stmt))
                added.append((table_name, column.name))
    return added

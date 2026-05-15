"""initial schema

Revision ID: 20260515_0001
Revises:
Create Date: 2026-05-15

This bootstrap migration delegates to SQLAlchemy `Base.metadata.create_all`
so the schema stays in sync with the ORM models without duplicating column
definitions. Subsequent migrations should be generated with
`alembic revision --autogenerate` and use explicit `op.create_table` /
`op.add_column` operations.
"""
from __future__ import annotations

from alembic import op

import backend.app.models  # noqa: F401  ensure metadata is populated
from backend.app.core.database import Base

revision = "20260515_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)

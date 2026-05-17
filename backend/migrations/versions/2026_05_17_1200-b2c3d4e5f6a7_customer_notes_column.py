"""customer_notes_column

Free-form notes field on Customer, edited from the chat panel.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-17 12:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('customers', sa.Column('notes', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('customers', 'notes')

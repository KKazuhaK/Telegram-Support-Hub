"""message_attachment_columns

Adds attachment_path / attachment_mime so the chat UI can send images.

Revision ID: a1b2c3d4e5f6
Revises: 231d946fa676
Create Date: 2026-05-17 09:30:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = '231d946fa676'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('message_records', sa.Column('attachment_path', sa.String(length=255), nullable=True))
    op.add_column('message_records', sa.Column('attachment_mime', sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column('message_records', 'attachment_mime')
    op.drop_column('message_records', 'attachment_path')

"""message_record_direction

Revision ID: c2aa8796a530
Revises: 09fde8b7adc6
Create Date: 2026-05-15 22:18:11.406199

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c2aa8796a530'
down_revision = '09fde8b7adc6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default='outbound' so the column can be added NOT NULL on a
    # table that already has rows — existing message records are treated
    # as outbound (the only kind that existed before this revision).
    op.add_column(
        'message_records',
        sa.Column('direction', sa.String(length=16), nullable=False, server_default='outbound'),
    )
    op.create_index(op.f('ix_message_records_direction'), 'message_records', ['direction'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_message_records_direction'), table_name='message_records')
    op.drop_column('message_records', 'direction')

"""add race_control_event

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'race_control_event',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('lap', sa.Integer(), nullable=True),
        sa.Column('driver', sa.String(), nullable=True),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('message', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['session.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_race_control_event_session_id', 'race_control_event', ['session_id'])
    op.create_index('ix_race_control_event_driver', 'race_control_event', ['driver'])


def downgrade() -> None:
    op.drop_index('ix_race_control_event_driver', table_name='race_control_event')
    op.drop_index('ix_race_control_event_session_id', table_name='race_control_event')
    op.drop_table('race_control_event')

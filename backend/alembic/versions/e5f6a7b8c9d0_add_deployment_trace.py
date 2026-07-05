"""add deployment_trace

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-05 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'deployment_trace',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('driver', sa.String(), nullable=False),
        sa.Column('constructor', sa.String(), nullable=True),
        sa.Column('top_speed_kmh', sa.Float(), nullable=True),
        sa.Column('total_clip_m', sa.Float(), nullable=False),
        sa.Column('max_clip_m', sa.Float(), nullable=False),
        sa.Column('n_straights', sa.Integer(), nullable=False),
        sa.Column('n_clips', sa.Integer(), nullable=False),
        sa.Column('straights_json', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['session.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_deployment_trace_session_id', 'deployment_trace', ['session_id'])
    op.create_index('ix_deployment_trace_driver', 'deployment_trace', ['driver'])


def downgrade() -> None:
    op.drop_index('ix_deployment_trace_driver', table_name='deployment_trace')
    op.drop_index('ix_deployment_trace_session_id', table_name='deployment_trace')
    op.drop_table('deployment_trace')

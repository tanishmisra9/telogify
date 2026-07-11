"""add quali_trace

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-07-11 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'k1l2m3n4o5p6'
down_revision: Union[str, Sequence[str], None] = 'j0k1l2m3n4o5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'quali_trace',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('driver', sa.String(), nullable=False),
        sa.Column('constructor', sa.String(), nullable=True),
        sa.Column('lap_time_s', sa.Float(), nullable=True),
        sa.Column('is_pole', sa.Boolean(), nullable=False),
        sa.Column('grid_m', sa.JSON(), nullable=True),
        sa.Column('corners_json', sa.JSON(), nullable=True),
        sa.Column('speed_kmh', sa.JSON(), nullable=True),
        sa.Column('throttle_pct', sa.JSON(), nullable=True),
        sa.Column('delta_s', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['session.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_quali_trace_session_id', 'quali_trace', ['session_id'])
    op.create_index('ix_quali_trace_driver', 'quali_trace', ['driver'])


def downgrade() -> None:
    op.drop_index('ix_quali_trace_driver', table_name='quali_trace')
    op.drop_index('ix_quali_trace_session_id', table_name='quali_trace')
    op.drop_table('quali_trace')

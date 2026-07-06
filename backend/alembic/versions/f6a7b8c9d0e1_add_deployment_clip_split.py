"""add deployment clip split columns

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-05 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('deployment_trace', sa.Column('total_depletion_m', sa.Float(), nullable=False, server_default='0'))
    op.add_column('deployment_trace', sa.Column('total_superclip_m', sa.Float(), nullable=False, server_default='0'))
    op.add_column('deployment_trace', sa.Column('max_clip_severity_ms2', sa.Float(), nullable=False, server_default='0'))
    op.alter_column('deployment_trace', 'total_depletion_m', server_default=None)
    op.alter_column('deployment_trace', 'total_superclip_m', server_default=None)
    op.alter_column('deployment_trace', 'max_clip_severity_ms2', server_default=None)


def downgrade() -> None:
    op.drop_column('deployment_trace', 'max_clip_severity_ms2')
    op.drop_column('deployment_trace', 'total_superclip_m')
    op.drop_column('deployment_trace', 'total_depletion_m')

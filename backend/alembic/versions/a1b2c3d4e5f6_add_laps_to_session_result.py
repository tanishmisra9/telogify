"""add laps to session_result

Revision ID: a1b2c3d4e5f6
Revises: 68a46bfef61c
Create Date: 2026-06-30 00:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '68a46bfef61c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('session_result', sa.Column('laps', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('session_result', 'laps')

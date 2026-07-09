"""add q1/q2/q3 segment times to session_result

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-07-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, Sequence[str], None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("session_result", sa.Column("q1_time_s", sa.Float(), nullable=True))
    op.add_column("session_result", sa.Column("q2_time_s", sa.Float(), nullable=True))
    op.add_column("session_result", sa.Column("q3_time_s", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("session_result", "q3_time_s")
    op.drop_column("session_result", "q2_time_s")
    op.drop_column("session_result", "q1_time_s")

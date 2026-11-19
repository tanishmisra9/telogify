"""add official starting grid and lapped gap to session_result

Revision ID: x9y0z1a2b3c4
Revises: w8x9y0z1a2b3
Create Date: 2026-11-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "x9y0z1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "w8x9y0z1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable columns with no CHECK: safe on a populated table for the start-time `alembic upgrade`.
    op.add_column("session_result", sa.Column("grid", sa.Integer(), nullable=True))
    op.add_column("session_result", sa.Column("lapped_gap_s", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("session_result", "lapped_gap_s")
    op.drop_column("session_result", "grid")

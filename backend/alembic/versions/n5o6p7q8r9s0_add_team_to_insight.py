"""add team to insight

Race insights had no structured constructor field (unlike quali_insight.team), so every
consumer that wants to color-code or group by team had to guess from prose. Mirrors
quali_insight.team exactly.

Revision ID: n5o6p7q8r9s0
Revises: m3n4o5p6q7r8
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "n5o6p7q8r9s0"
down_revision: Union[str, Sequence[str], None] = "m3n4o5p6q7r8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "insight",
        sa.Column("team", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("insight", "team")

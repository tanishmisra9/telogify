"""add race_start

Revision ID: u6v7w8x9y0z1
Revises: t5u6v7w8x9y0
Create Date: 2026-11-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "u6v7w8x9y0z1"
down_revision: Union[str, Sequence[str], None] = "t5u6v7w8x9y0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "race_start",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("driver", sa.String(), nullable=False),
        sa.Column("constructor", sa.String(), nullable=True),
        sa.Column("t_0_100_s", sa.Float(), nullable=False),
        sa.Column("t_0_200_s", sa.Float(), nullable=True),
        sa.Column("v_75m_kmh", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["session.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_race_start_session_id", "race_start", ["session_id"])
    op.create_index("ix_race_start_driver", "race_start", ["driver"])


def downgrade() -> None:
    op.drop_index("ix_race_start_driver", table_name="race_start")
    op.drop_index("ix_race_start_session_id", table_name="race_start")
    op.drop_table("race_start")

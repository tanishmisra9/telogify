"""add race_restart

Revision ID: y0z1a2b3c4d5
Revises: x9y0z1a2b3c4
Create Date: 2026-11-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "y0z1a2b3c4d5"
down_revision: Union[str, Sequence[str], None] = "x9y0z1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "race_restart",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("start_index", sa.Integer(), nullable=False),
        sa.Column("driver", sa.String(), nullable=False),
        sa.Column("constructor", sa.String(), nullable=True),
        sa.Column("t_0_100_s", sa.Float(), nullable=False),
        sa.Column("t_0_200_s", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["session.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_race_restart_session_id", "race_restart", ["session_id"])
    op.create_index("ix_race_restart_driver", "race_restart", ["driver"])


def downgrade() -> None:
    op.drop_index("ix_race_restart_driver", table_name="race_restart")
    op.drop_index("ix_race_restart_session_id", table_name="race_restart")
    op.drop_table("race_restart")

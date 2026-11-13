"""add race_start_skip

Revision ID: w8x9y0z1a2b3
Revises: v7w8x9y0z1a2
Create Date: 2026-11-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "w8x9y0z1a2b3"
down_revision: Union[str, Sequence[str], None] = "v7w8x9y0z1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A new, empty table, so the CHECK is added plainly (no NOT VALID needed).
    op.create_table(
        "race_start_skip",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("driver", sa.String(), nullable=False),
        sa.Column("constructor", sa.String(), nullable=True),
        sa.Column("reason", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["session.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "reason IN ('did_not_start','late_launch','moving_at_start','too_slow','no_200',"
            "'no_data','no_common_start','too_few_timed')",
            name="ck_race_start_skip_reason",
        ),
    )
    op.create_index("ix_race_start_skip_session_id", "race_start_skip", ["session_id"])
    op.create_index("ix_race_start_skip_driver", "race_start_skip", ["driver"])


def downgrade() -> None:
    op.drop_index("ix_race_start_skip_driver", table_name="race_start_skip")
    op.drop_index("ix_race_start_skip_session_id", table_name="race_start_skip")
    op.drop_table("race_start_skip")
